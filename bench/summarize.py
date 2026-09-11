"""Convert raw request and GPU records into publication-facing summaries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict
from typing import Any

import numpy as np

from bench.schema import GpuSample, RequestResult, SummaryRecord


def summarize_records(
    request_records: Sequence[RequestResult | Mapping[str, object]],
    gpu_samples: Sequence[GpuSample | Mapping[str, object]],
    *,
    experiment_id: str,
    run_id: str,
    measurement_duration_s: float,
    warmup_requests: int = 0,
) -> SummaryRecord:
    """Compute metrics while excluding warm-up records from every aggregate."""

    if measurement_duration_s <= 0:
        raise ValueError("measurement_duration_s must be greater than 0")
    if warmup_requests < 0:
        raise ValueError("warmup_requests must be non-negative")

    measured = [
        record
        for record in request_records
        if int(_field(record, "request_index")) >= warmup_requests
    ]
    successes = [record for record in measured if _is_success(record)]
    failures = [record for record in measured if not _is_success(record)]
    latencies = _numbers(successes, "latency_ms")
    queue_times = _numbers(measured, "queue_ms")
    backend_times = _numbers(measured, "backend_ms")
    batch_sizes = _numbers(measured, "batch_size")
    output_tokens = _numbers(successes, "output_tokens")
    drift_ms = [
        (float(_field(record, "actual_arrival_s")) - float(_field(record, "target_arrival_s")))
        * 1000
        for record in measured
    ]
    deadline_values = [
        bool(_field(record, "deadline_met"))
        for record in successes
        if _field(record, "deadline_met") is not None
    ]
    usable_gpu = [sample for sample in gpu_samples if _field(sample, "error_type") is None]
    gpu_utilization = _numbers(usable_gpu, "utilization_gpu_percent")
    vram_used = _numbers(usable_gpu, "memory_used_mb")
    power_draw = _numbers(usable_gpu, "power_draw_w")

    return SummaryRecord(
        schema_version=1,
        experiment_id=experiment_id,
        run_id=run_id,
        offered_request_rate=len(measured) / measurement_duration_s,
        achieved_request_throughput=len(successes) / measurement_duration_s,
        achieved_output_token_throughput=sum(output_tokens, 0.0)
        / measurement_duration_s,
        success_count=len(successes),
        failure_count=len(failures),
        p50_latency_ms=_quantile(latencies, 0.50),
        p95_latency_ms=_quantile(latencies, 0.95),
        p99_latency_ms=_quantile(latencies, 0.99),
        mean_queue_ms=_mean(queue_times),
        p95_queue_ms=_quantile(queue_times, 0.95),
        mean_backend_ms=_mean(backend_times),
        mean_batch_size=_mean(batch_sizes),
        slo_attainment_percent=(
            100.0 * sum(deadline_values) / len(deadline_values)
            if deadline_values
            else None
        ),
        mean_gpu_utilization_percent=_mean(gpu_utilization),
        max_vram_used_mb=max(vram_used) if vram_used else None,
        mean_power_draw_w=_mean(power_draw),
        p95_arrival_drift_ms=_quantile(drift_ms, 0.95),
    )


def summary_to_mapping(summary: SummaryRecord) -> dict[str, object]:
    """Return the stable JSON representation used by storage and plotting."""

    return asdict(summary)


def _is_success(record: RequestResult | Mapping[str, object]) -> bool:
    status_code = _field(record, "status_code")
    return (
        _field(record, "error_type") is None
        and isinstance(status_code, int)
        and not isinstance(status_code, bool)
        and 200 <= status_code < 300
    )


def _numbers(
    records: Sequence[RequestResult | GpuSample | Mapping[str, object]], key: str
) -> list[float]:
    values: list[float] = []
    for record in records:
        value = _field(record, key)
        if value is not None:
            values.append(float(value))
    return values


def _field(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key)


def _mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _quantile(values: Sequence[float], quantile: float) -> float | None:
    return float(np.quantile(values, quantile)) if values else None
