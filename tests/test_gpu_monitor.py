"""Tests for nvidia-smi command construction, parsing, and failure records."""

from __future__ import annotations

from pathlib import Path

from bench.gpu_monitor import (
    QUERY_ARGUMENT,
    nvidia_smi_command,
    parse_nvidia_smi_output,
    sample_gpu,
    telemetry_available,
)


FIXTURE = Path(__file__).parent / "fixtures" / "nvidia_smi_sample.csv"


def test_command_uses_explicit_query_fields() -> None:
    command = nvidia_smi_command()

    assert command == [
        "nvidia-smi",
        f"--query-gpu={QUERY_ARGUMENT}",
        "--format=csv,noheader,nounits",
    ]


def test_fixture_parser_preserves_identifiers_and_measurements() -> None:
    samples = parse_nvidia_smi_output(
        FIXTURE.read_text(encoding="utf-8"), "experiment-1", "run-1"
    )

    assert len(samples) == 1
    sample = samples[0]
    assert sample.experiment_id == "experiment-1"
    assert sample.run_id == "run-1"
    assert sample.name == "NVIDIA GeForce RTX 3060"
    assert sample.utilization_gpu_percent == 12.0
    assert sample.memory_used_mb == 1024.0
    assert sample.memory_total_mb == 12288.0
    assert sample.power_draw_w == 18.5
    assert telemetry_available(samples)


def test_parser_keeps_unavailable_numeric_values_as_none() -> None:
    samples = parse_nvidia_smi_output(
        "timestamp, 0, GPU, N/A, 1, 2, N/A, N/A\n", "experiment-1", "run-1"
    )

    assert samples[0].utilization_gpu_percent is None
    assert samples[0].power_draw_w is None
    assert samples[0].temperature_gpu_c is None


def test_missing_nvidia_smi_becomes_explicit_error_sample() -> None:
    samples = sample_gpu(
        "experiment-1", "run-1", executable="nvidia-smi-command-that-is-not-installed"
    )

    assert len(samples) == 1
    assert samples[0].error_type == "FileNotFoundError"
    assert not telemetry_available(samples)
