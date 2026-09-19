"""Tests for run-level final-matrix analysis."""

from __future__ import annotations

import pytest

from bench.analyze_final import (
    RunResult,
    aggregate_runs,
    mean_ci95,
    paired_effects,
    parse_run_id,
)


def _run(mode: str, rate: float, repetition: int, p95: float) -> RunResult:
    run_id = f"{mode}-rate-{str(rate).replace('.', 'p')}-rep-{repetition}"
    return RunResult(
        run_id=run_id,
        mode=mode,
        rate=rate,
        repetition=repetition,
        summary={
            "achieved_request_throughput": rate,
            "p50_latency_ms": p95 - 20.0,
            "p95_latency_ms": p95,
            "p99_latency_ms": p95 + 20.0,
            "mean_queue_ms": 1.0,
            "mean_backend_ms": p95 - 1.0,
            "mean_batch_size": 2.0,
            "mean_gpu_utilization_percent": 50.0,
            "max_vram_used_mb": 4096.0,
            "mean_power_draw_w": 90.0,
            "p95_arrival_drift_ms": 2.0,
        },
    )


def test_parse_run_id_handles_underscored_mode() -> None:
    assert parse_run_id("pass_through-rate-1p8-rep-3") == (
        "pass_through",
        1.8,
        3,
    )


def test_mean_ci95_uses_run_level_student_t_interval() -> None:
    result = mean_ci95([100.0, 110.0, 120.0])

    assert result["n"] == 3
    assert result["mean"] == 110.0
    assert result["half_width"] == pytest.approx(24.841377117)
    assert result["lower"] == pytest.approx(85.158622883)
    assert result["upper"] == pytest.approx(134.841377117)


def test_aggregate_runs_preserves_run_ids_and_repetition_unit() -> None:
    runs = [_run("direct", 0.5, repetition, 100.0 + repetition) for repetition in (1, 2, 3)]

    row = next(
        item
        for item in aggregate_runs(runs)
        if item["mode"] == "direct" and item["rate_rps"] == 0.5
    )

    assert row["repetitions"] == [1, 2, 3]
    assert row["p95_latency_ms"]["n"] == 3  # type: ignore[index]
    assert row["p95_latency_ms"]["mean"] == 102.0  # type: ignore[index]


def test_paired_effects_pair_matching_repetition_seeds() -> None:
    runs = []
    for repetition in (1, 2, 3):
        runs.append(_run("direct", 0.5, repetition, 100.0 + repetition))
        runs.append(_run("pass_through", 0.5, repetition, 110.0 + repetition))

    effect = next(
        item
        for item in paired_effects(runs)
        if item["comparison"] == "Proxy minus direct" and item["rate_rps"] == 0.5
    )

    assert effect["p95_latency_ms_absolute"]["n"] == 3  # type: ignore[index]
    assert effect["p95_latency_ms_absolute"]["mean"] == 10.0  # type: ignore[index]
    assert effect["p95_latency_ms_relative_percent"]["mean"] == pytest.approx(
        9.804549844
    )
