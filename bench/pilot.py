"""Run the EXP-002 fixed-window pilot through the local ADIP gateway."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

import httpx

from bench.calibration import build_calibration_requests
from bench.client import AdipClient
from bench.config import ConfigError, load_experiment_config
from bench.gpu_monitor import monitor_gpu
from bench.prompts import HuggingFaceTokenCounter, build_prompt_set
from bench.runner import run_open_loop
from bench.schema import ExperimentConfig, PlannedRequest
from bench.storage import append_jsonl, write_json_atomic
from bench.summarize import summarize_records, summary_to_mapping


async def run_pilot(config: ExperimentConfig) -> list[dict[str, object]]:
    """Run every configured wait/rate pair and write raw pilot evidence."""

    if not config.pilot_rates_rps:
        raise ConfigError("experiment.pilot_rates_rps is required for EXP-002")
    if not config.pilot_wait_windows_ms:
        raise ConfigError(
            "experiment.pilot_wait_windows_ms is required for EXP-002"
        )

    tokenizer = HuggingFaceTokenCounter(config.model.model_id, config.model.revision)
    prompts = build_prompt_set(
        tokenizer,
        config.workload.prompt_buckets,
        prompts_per_bucket=4,
        seed=config.workload.arrival.seed,
    )
    output_root = config.output_dir / config.name
    output_root.mkdir(parents=True, exist_ok=True)
    log_root = config.output_dir.parent / "system" / config.name
    summaries: list[dict[str, object]] = []

    for wait_index, wait_ms in enumerate(config.pilot_wait_windows_ms):
        gateway, log_handle = _start_gateway(config, wait_ms, log_root)
        try:
            await _wait_for_gateway(config, gateway)
            client = AdipClient(base_url="http://127.0.0.1:8000", timeout_s=120.0)
            try:
                for rate_index, rate_per_s in enumerate(config.pilot_rates_rps):
                    summaries.append(
                        await _run_condition(
                            config,
                            wait_ms,
                            rate_per_s,
                            prompts,
                            output_root,
                            client,
                        )
                    )
                    if rate_index < len(config.pilot_rates_rps) - 1:
                        await asyncio.sleep(config.cooldown_s)
            finally:
                await client.aclose()
        finally:
            _stop_gateway(gateway, log_handle)
        if wait_index < len(config.pilot_wait_windows_ms) - 1:
            await asyncio.sleep(config.cooldown_s)

    write_json_atomic(
        config.output_dir.parent / "summaries" / "generated" / f"{config.name}.json",
        {"experiment_id": config.name, "summaries": summaries},
    )
    return summaries


async def _run_condition(
    config: ExperimentConfig,
    wait_ms: int,
    rate_per_s: float,
    prompts: tuple[object, ...],
    output_root: Path,
    client: AdipClient,
) -> dict[str, object]:
    rate_label = str(rate_per_s).replace(".", "p")
    run_id = f"wait-{wait_ms}ms-rate-{rate_label}"
    run_dir = output_root / f"wait-{wait_ms}ms" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    request_path = run_dir / "requests.jsonl"
    gpu_path = run_dir / "gpu.jsonl"
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "schema_version": 1,
        "experiment_id": config.name,
        "run_id": run_id,
        "status": "started",
        "started_at_utc": _utc_now(),
        "rate_per_s": rate_per_s,
        "max_wait_ms": wait_ms,
        "max_batch_size": config.max_batch_size,
        "model": asdict(config.model),
        "workload": config.workload.name,
        "warmup_requests": config.workload.warmup_requests,
        "measurement_duration_s": config.workload.arrival.duration_s,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "tokenizer_revision": config.model.revision,
        "gateway_mode": config.gateway_mode,
    }
    write_json_atomic(manifest_path, manifest)

    for warmup_index in range(config.workload.warmup_requests):
        warmup = build_calibration_requests(
            config, rate_per_s, run_id, prompts, policy="fixed"
        )[0]
        warmup = PlannedRequest(
            **{**asdict(warmup), "request_index": -warmup_index - 1}
        )
        await client.infer(warmup)

    requests = build_calibration_requests(
        config, rate_per_s, run_id, prompts, policy="fixed"
    )
    stop_event = asyncio.Event()
    gpu_task = asyncio.create_task(
        monitor_gpu(
            config.name,
            run_id,
            config.workload.arrival.duration_s + 3.0,
            stop_event=stop_event,
        )
    )
    try:
        results = await run_open_loop(
            requests,
            client,
            results_path=request_path,
            start_delay_s=2.0,
            harness_drift_threshold_ms=config.harness_drift_threshold_ms,
            harness_error_threshold=config.harness_error_threshold,
        )
    finally:
        stop_event.set()
        gpu_samples = await gpu_task

    for sample in gpu_samples:
        append_jsonl(gpu_path, asdict(sample))

    summary = summarize_records(
        results,
        gpu_samples,
        experiment_id=config.name,
        run_id=run_id,
        measurement_duration_s=config.workload.arrival.duration_s,
        warmup_requests=0,
    )
    write_json_atomic(run_dir / "summary.json", summary_to_mapping(summary))
    manifest.update({"status": "complete", "ended_at_utc": _utc_now()})
    write_json_atomic(manifest_path, manifest)
    return summary_to_mapping(summary)


def _start_gateway(
    config: ExperimentConfig, wait_ms: int, log_root: Path
) -> tuple[subprocess.Popen[bytes], TextIO]:
    """Start one isolated gateway process for a fixed wait setting."""

    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / f"gateway-wait-{wait_ms}ms.log"
    log_handle = log_path.open("w", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "ADIP_BACKEND_KIND": "vllm",
            "ADIP_GATEWAY_MODE": "batched",
            "ADIP_BATCH_POLICY": "fixed",
            "ADIP_BATCH_MAX_SIZE": str(config.max_batch_size),
            "ADIP_BATCH_MAX_WAIT_MS": str(wait_ms),
            "ADIP_VLLM_BASE_URL": "http://127.0.0.1:8001",
            "ADIP_VLLM_MODEL": config.model.served_name,
            "ADIP_APP_HOST": "127.0.0.1",
            "ADIP_APP_PORT": "8000",
            "ADIP_RESEARCH_TELEMETRY": "true",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "gateway.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=Path.cwd(),
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    return process, log_handle


async def _wait_for_gateway(
    config: ExperimentConfig, process: subprocess.Popen[bytes]
) -> None:
    deadline = asyncio.get_running_loop().time() + 60.0
    async with httpx.AsyncClient(timeout=2.0) as client:
        while asyncio.get_running_loop().time() < deadline:
            if process.poll() is not None:
                raise RuntimeError("gateway exited before its health endpoint became ready")
            try:
                response = await client.get(config.health_url)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    raise TimeoutError("gateway health endpoint did not become ready within 60 seconds")


def _stop_gateway(process: subprocess.Popen[bytes], log_handle: TextIO) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=20)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    log_handle.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ADIP EXP-002 pilot.")
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_experiment_config(args.config)
    print(
        json.dumps(
            {
                "config": str(config.source_path),
                "rates": config.pilot_rates_rps,
                "wait_windows_ms": config.pilot_wait_windows_ms,
            }
        )
    )
    asyncio.run(run_pilot(config))


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, check=False, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _git_dirty() -> bool:
    result = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, check=False, text=True
    )
    return bool(result.stdout.strip())


if __name__ == "__main__":
    main()
