"""Primary-model direct-vLLM calibration driver for EXP-001."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bench.arrivals import constant_arrivals
from bench.client import DirectVllmClient
from bench.config import ConfigError, load_experiment_config
from bench.gpu_monitor import monitor_gpu
from bench.prompts import HuggingFaceTokenCounter, build_prompt_set
from bench.runner import run_open_loop
from bench.schema import ExperimentConfig, PlannedRequest
from bench.storage import append_jsonl, write_json_atomic
from bench.summarize import summarize_records, summary_to_mapping


def build_calibration_requests(
    config: ExperimentConfig,
    rate_per_s: float,
    run_id: str,
    prompts: tuple[object, ...],
) -> tuple[PlannedRequest, ...]:
    """Create all request records before a calibration rate begins."""

    if rate_per_s <= 0:
        raise ValueError("rate_per_s must be greater than 0")
    if not prompts:
        raise ValueError("prompts must not be empty")
    offsets = constant_arrivals(rate_per_s, config.workload.arrival.duration_s)
    return tuple(
        PlannedRequest(
            schema_version=1,
            experiment_id=config.name,
            run_id=run_id,
            request_index=index,
            policy="direct",
            model=config.model.model_id,
            workload=config.workload.name,
            seed=config.workload.arrival.seed,
            arrival_offset_s=offset,
            prompt=prompts[index % len(prompts)].text,  # type: ignore[union-attr]
            input_tokens=prompts[index % len(prompts)].input_tokens,  # type: ignore[union-attr]
            max_tokens=config.model.max_tokens,
            temperature=config.model.temperature,
            deadline_ms=None,
        )
        for index, offset in enumerate(offsets)
    )


async def run_calibration(config: ExperimentConfig) -> list[dict[str, object]]:
    """Run every configured direct-vLLM rate and write raw evidence."""

    if config.calibration_rates_rps is None:
        raise ConfigError("experiment.calibration_rates_rps is required for EXP-001")

    tokenizer = HuggingFaceTokenCounter(config.model.model_id, config.model.revision)
    prompts = build_prompt_set(
        tokenizer,
        config.workload.prompt_buckets,
        prompts_per_bucket=4,
        seed=config.workload.arrival.seed,
    )
    output_root = config.output_dir / config.name
    output_root.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, object]] = []
    client = DirectVllmClient(base_url="http://127.0.0.1:8001", timeout_s=120.0)

    try:
        for rate_per_s in config.calibration_rates_rps:
            summaries.append(
                await _run_rate(config, rate_per_s, prompts, output_root, client)
            )
    finally:
        await client.aclose()

    write_json_atomic(
        config.output_dir.parent / "summaries" / "generated" / f"{config.name}.json",
        {"experiment_id": config.name, "summaries": summaries},
    )
    return summaries


async def _run_rate(
    config: ExperimentConfig,
    rate_per_s: float,
    prompts: tuple[object, ...],
    output_root: Path,
    client: DirectVllmClient,
) -> dict[str, object]:
    rate_label = str(rate_per_s).replace(".", "p")
    run_id = f"rate-{rate_label}"
    run_dir = output_root / run_id
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
        "model": asdict(config.model),
        "workload": config.workload.name,
        "warmup_requests": config.workload.warmup_requests,
        "measurement_duration_s": config.workload.arrival.duration_s,
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "tokenizer_revision": config.model.revision,
    }
    write_json_atomic(manifest_path, manifest)

    for warmup_index in range(config.workload.warmup_requests):
        warmup = build_calibration_requests(config, rate_per_s, run_id, prompts)[0]
        warmup = PlannedRequest(
            **{**asdict(warmup), "request_index": -warmup_index - 1}
        )
        await client.infer(warmup)

    requests = build_calibration_requests(config, rate_per_s, run_id, prompts)
    stop_event = asyncio.Event()
    gpu_task = asyncio.create_task(
        monitor_gpu(
            config.name,
            run_id,
            config.workload.arrival.duration_s + 3.0,
            stop_event=stop_event,
        )
    )
    results = await run_open_loop(
        requests,
        client,
        results_path=request_path,
        start_delay_s=2.0,
        harness_drift_threshold_ms=10.0,
    )
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run ADIP EXP-001 calibration.")
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_experiment_config(args.config)
    print(json.dumps({"config": str(config.source_path), "rates": config.calibration_rates_rps}))
    asyncio.run(run_calibration(config))


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
