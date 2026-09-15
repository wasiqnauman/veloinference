"""Run the EXP-003 primary final matrix on the local services."""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bench.calibration import build_calibration_requests
from bench.client import AdipClient, DirectVllmClient, InferenceClient
from bench.config import ConfigError, load_experiment_config
from bench.gpu_monitor import monitor_gpu
from bench.pilot import _start_gateway, _stop_gateway, _wait_for_gateway
from bench.prompts import HuggingFaceTokenCounter, build_prompt_set
from bench.runner import HarnessOverloadError, run_open_loop
from bench.schema import ExperimentConfig, PlannedRequest, PreparedPrompt
from bench.storage import append_jsonl, write_json_atomic
from bench.summarize import summarize_records, summary_to_mapping


async def run_final(config: ExperimentConfig) -> list[dict[str, object]]:
    """Run every mode, rate, and repetition in the committed final matrix."""

    if not config.final_modes:
        raise ConfigError("experiment.final_modes is required for EXP-003")
    if not config.final_rates_rps:
        raise ConfigError("experiment.final_rates_rps is required for EXP-003")
    if not config.final_repetitions:
        raise ConfigError("experiment.final_repetitions is required for EXP-003")

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

    for mode in config.final_modes:
        gateway = None
        log_handle = None
        wait_ms = 0
        gateway_mode = "pass_through"
        policy = "fixed"
        if mode == "fixed":
            gateway_mode = "batched"
            wait_ms = config.max_wait_ms
        elif mode == "adaptive":
            gateway_mode = "batched"
            policy = "adaptive"
            wait_ms = config.adaptive_max_wait_ms
        elif mode != "direct":
            gateway_mode = "pass_through"

        if mode != "direct":
            gateway, log_handle = _start_gateway(
                config,
                wait_ms,
                log_root,
                gateway_mode=gateway_mode,
                policy=policy,
                log_label=mode,
            )
            await _wait_for_gateway(config, gateway)

        client: InferenceClient
        if mode == "direct":
            client = DirectVllmClient(base_url="http://127.0.0.1:8001", timeout_s=120.0)
        else:
            client = AdipClient(base_url="http://127.0.0.1:8000", timeout_s=120.0)

        try:
            for repetition_index, repetition in enumerate(config.final_repetitions):
                repetition_seed = config.repetition_seeds[repetition_index]
                for rate_index, rate_per_s in enumerate(config.final_rates_rps):
                    run_id = _run_id(mode, rate_per_s, repetition)
                    existing_summary = _load_existing_summary(
                        output_root / mode / run_id,
                        run_id=run_id,
                        resume_existing=config.resume_existing,
                    )
                    if existing_summary is not None:
                        summaries.append(existing_summary)
                        continue
                    try:
                        summary = await _run_condition(
                            config,
                            mode,
                            wait_ms,
                            repetition,
                            repetition_seed,
                            rate_per_s,
                            prompts,
                            output_root,
                            client,
                        )
                    except HarnessOverloadError as exc:
                        run_dir = output_root / mode / run_id
                        _mark_invalid_harness(run_dir, str(exc))
                        summary = _invalid_summary(
                            config, mode, rate_per_s, repetition, str(exc)
                        )
                    summaries.append(summary)
                    is_last = (
                        repetition_index == len(config.final_repetitions) - 1
                        and rate_index == len(config.final_rates_rps) - 1
                    )
                    if not is_last:
                        await asyncio.sleep(config.cooldown_s)
        finally:
            await client.aclose()
            if gateway is not None and log_handle is not None:
                _stop_gateway(gateway, log_handle)

    write_json_atomic(
        config.output_dir.parent / "summaries" / "generated" / f"{config.name}.json",
        {"experiment_id": config.name, "summaries": summaries},
    )
    return summaries


async def _run_condition(
    config: ExperimentConfig,
    mode: str,
    wait_ms: int,
    repetition: int,
    repetition_seed: int,
    rate_per_s: float,
    prompts: tuple[PreparedPrompt, ...],
    output_root: Path,
    client: InferenceClient,
) -> dict[str, object]:
    run_id = _run_id(mode, rate_per_s, repetition)
    run_dir = output_root / mode / run_id
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
        "mode": mode,
        "rate_per_s": rate_per_s,
        "repetition": repetition,
        "seed": repetition_seed,
        "max_wait_ms": wait_ms,
        "max_batch_size": config.max_batch_size,
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
        warmup = build_calibration_requests(
            config,
            rate_per_s,
            run_id,
            prompts,
            policy=mode,
            seed=repetition_seed,
        )[0]
        warmup = PlannedRequest(
            **{**asdict(warmup), "request_index": -warmup_index - 1}
        )
        await client.infer(warmup)

    requests = build_calibration_requests(
        config,
        rate_per_s,
        run_id,
        prompts,
        policy=mode,
        seed=repetition_seed,
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


def _run_id(mode: str, rate_per_s: float, repetition: int) -> str:
    """Return the stable directory identifier for one matrix condition."""

    rate_label = str(rate_per_s).replace(".", "p")
    return f"{mode}-rate-{rate_label}-rep-{repetition}"


def _load_existing_summary(
    run_dir: Path, *, run_id: str, resume_existing: bool
) -> dict[str, object] | None:
    """Reuse complete evidence or reject an unsafe existing run directory."""

    if not run_dir.exists():
        return None
    if not resume_existing:
        raise ConfigError(
            f"run directory already exists: {run_dir}; set "
            "experiment.resume_existing=true to reuse complete evidence"
        )

    manifest_path = run_dir / "manifest.json"
    summary_path = run_dir / "summary.json"
    if not manifest_path.exists():
        raise ConfigError(
            f"existing run is incomplete: {run_dir}; archive it before resuming"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ConfigError(f"existing manifest is invalid: {run_dir}")
    if manifest.get("status") == "invalid_harness":
        return _invalid_summary_from_manifest(manifest, run_id)
    if manifest.get("status") != "complete":
        raise ConfigError(
            f"existing run is incomplete: {run_dir}; archive it before resuming"
        )
    if not summary_path.exists():
        raise ConfigError(
            f"existing run is incomplete: {run_dir}; archive it before resuming"
        )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or summary.get("run_id") != run_id:
        raise ConfigError(f"existing summary does not match run id: {run_dir}")
    return summary


def _mark_invalid_harness(run_dir: Path, reason: str) -> None:
    """Mark a completed request trace as invalid without fabricating metrics."""

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ConfigError(f"manifest is invalid and cannot be marked: {run_dir}")
    manifest.update(
        {
            "status": "invalid_harness",
            "ended_at_utc": _utc_now(),
            "invalid_reason": reason,
        }
    )
    write_json_atomic(manifest_path, manifest)


def _invalid_summary(
    config: ExperimentConfig,
    mode: str,
    rate_per_s: float,
    repetition: int,
    reason: str,
) -> dict[str, object]:
    """Create an aggregate marker that analysis must exclude from metrics."""

    return {
        "schema_version": 1,
        "experiment_id": config.name,
        "run_id": _run_id(mode, rate_per_s, repetition),
        "status": "invalid_harness",
        "valid": False,
        "invalid_reason": reason,
    }


def _invalid_summary_from_manifest(
    manifest: dict[str, object], run_id: str
) -> dict[str, object]:
    """Reconstruct a terminal invalid marker during a resumed run."""

    return {
        "schema_version": 1,
        "experiment_id": manifest.get("experiment_id"),
        "run_id": run_id,
        "status": "invalid_harness",
        "valid": False,
        "invalid_reason": manifest.get("invalid_reason", "unknown harness error"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ADIP EXP-003 matrix.")
    parser.add_argument("--config", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_experiment_config(args.config)
    print(
        json.dumps(
            {
                "config": str(config.source_path),
                "modes": config.final_modes,
                "rates": config.final_rates_rps,
                "repetitions": config.final_repetitions,
            }
        )
    )
    asyncio.run(run_final(config))


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
