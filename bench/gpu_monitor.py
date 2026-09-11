"""Independent local GPU telemetry collection through ``nvidia-smi``."""

from __future__ import annotations

import asyncio
import csv
import subprocess
from collections.abc import Sequence
from datetime import UTC, datetime
from time import monotonic

from bench.schema import GpuSample

QUERY_FIELDS = (
    "timestamp",
    "index",
    "name",
    "utilization.gpu",
    "memory.used",
    "memory.total",
    "power.draw",
    "temperature.gpu",
)
QUERY_ARGUMENT = ",".join(QUERY_FIELDS)


def nvidia_smi_command(executable: str = "nvidia-smi") -> list[str]:
    """Return the fixed query command used for every telemetry sample."""

    return [
        executable,
        f"--query-gpu={QUERY_ARGUMENT}",
        "--format=csv,noheader,nounits",
    ]


def parse_nvidia_smi_output(
    output: str,
    experiment_id: str,
    run_id: str,
) -> tuple[GpuSample, ...]:
    """Parse one successful CSV response into one sample per visible GPU."""

    samples: list[GpuSample] = []
    for line_number, row in enumerate(csv.reader(output.splitlines()), 1):
        if not row or not any(field.strip() for field in row):
            continue
        if len(row) != len(QUERY_FIELDS):
            raise ValueError(
                f"nvidia-smi row {line_number} has {len(row)} fields; "
                f"expected {len(QUERY_FIELDS)}"
            )
        values = [field.strip() for field in row]
        samples.append(
            GpuSample(
                schema_version=1,
                experiment_id=experiment_id,
                run_id=run_id,
                sampled_at_utc=values[0],
                index=values[1] or None,
                name=values[2] or None,
                utilization_gpu_percent=_optional_float(values[3]),
                memory_used_mb=_optional_float(values[4]),
                memory_total_mb=_optional_float(values[5]),
                power_draw_w=_optional_float(values[6]),
                temperature_gpu_c=_optional_float(values[7]),
                error_type=None,
            )
        )
    if not samples:
        raise ValueError("nvidia-smi returned no GPU rows")
    return tuple(samples)


def sample_gpu(
    experiment_id: str,
    run_id: str,
    *,
    executable: str = "nvidia-smi",
    timeout_s: float = 5.0,
) -> tuple[GpuSample, ...]:
    """Collect one sample, returning explicit error records on failure."""

    sampled_at = _utc_now()
    try:
        completed = subprocess.run(
            nvidia_smi_command(executable),
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return (_error_sample(experiment_id, run_id, sampled_at, type(exc).__name__),)

    if completed.returncode != 0:
        return (
            _error_sample(
                experiment_id,
                run_id,
                sampled_at,
                f"NvidiaSmiExitCode{completed.returncode}",
            ),
        )
    try:
        return parse_nvidia_smi_output(completed.stdout, experiment_id, run_id)
    except ValueError as exc:
        return (_error_sample(experiment_id, run_id, sampled_at, type(exc).__name__),)


async def monitor_gpu(
    experiment_id: str,
    run_id: str,
    duration_s: float,
    *,
    interval_s: float = 1.0,
    executable: str = "nvidia-smi",
    stop_event: asyncio.Event | None = None,
) -> list[GpuSample]:
    """Sample independently until duration expires or ``stop_event`` is set."""

    if duration_s <= 0:
        raise ValueError("duration_s must be greater than 0")
    if interval_s <= 0:
        raise ValueError("interval_s must be greater than 0")

    started = monotonic()
    samples: list[GpuSample] = []
    while monotonic() - started < duration_s:
        samples.extend(
            await asyncio.to_thread(
                sample_gpu,
                experiment_id,
                run_id,
                executable=executable,
            )
        )
        if stop_event is not None and stop_event.is_set():
            break
        remaining = duration_s - (monotonic() - started)
        if remaining > 0:
            await asyncio.sleep(min(interval_s, remaining))
    return samples


def telemetry_available(samples: Sequence[GpuSample]) -> bool:
    """Return whether at least one sample contains usable GPU measurements."""

    return any(sample.error_type is None for sample in samples)


def _optional_float(value: str) -> float | None:
    if value.upper() in {"N/A", "NA", ""}:
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"invalid nvidia-smi numeric value: {value!r}") from exc


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _error_sample(
    experiment_id: str,
    run_id: str,
    sampled_at_utc: str,
    error_type: str,
) -> GpuSample:
    return GpuSample(
        schema_version=1,
        experiment_id=experiment_id,
        run_id=run_id,
        sampled_at_utc=sampled_at_utc,
        index=None,
        name=None,
        utilization_gpu_percent=None,
        memory_used_mb=None,
        memory_total_mb=None,
        power_draw_w=None,
        temperature_gpu_c=None,
        error_type=error_type,
    )
