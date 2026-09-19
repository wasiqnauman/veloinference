"""Tests for run-level final-matrix analysis."""

from __future__ import annotations

import json

import pytest

from bench.analyze_final import (
    MODES,
    RATES,
    REPETITIONS,
    RunResult,
    aggregate_runs,
    load_terminal_matrix,
    mean_ci95,
    mean_outer_group_size_per_call,
    paired_effects,
    parse_run_id,
    plot_mechanism,
    plot_overview,
    write_analysis_json,
    write_effect_table,
    write_primary_table,
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
            "mean_outer_group_size_per_call": 2.0,
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


def test_outer_group_mean_weights_backend_calls_not_requests(tmp_path) -> None:
    requests_path = tmp_path / "requests.jsonl"
    records = [
        {"request_index": 0, "batch_id": "singleton", "batch_size": 1},
        {"request_index": 1, "batch_id": "triple", "batch_size": 3},
        {"request_index": 2, "batch_id": "triple", "batch_size": 3},
        {"request_index": 3, "batch_id": "triple", "batch_size": 3},
    ]
    requests_path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )

    assert mean_outer_group_size_per_call(requests_path) == 2.0


def test_complete_matrix_generates_all_publication_artifacts(tmp_path) -> None:
    raw_root = tmp_path / "raw"
    for mode_index, mode in enumerate(MODES):
        for rate in RATES:
            for repetition in REPETITIONS:
                run = _run(
                    mode,
                    rate,
                    repetition,
                    p95=100.0 + 10.0 * mode_index + rate + repetition,
                )
                run_dir = raw_root / mode / run.run_id
                run_dir.mkdir(parents=True)
                (run_dir / "manifest.json").write_text(
                    json.dumps({"run_id": run.run_id, "status": "complete"}),
                    encoding="utf-8",
                )
                (run_dir / "summary.json").write_text(
                    json.dumps({"run_id": run.run_id, **run.summary}),
                    encoding="utf-8",
                )
                (run_dir / "requests.jsonl").write_text(
                    json.dumps(
                        {
                            "request_index": 0,
                            "batch_id": run.run_id,
                            "batch_size": 1,
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

    runs, excluded = load_terminal_matrix(raw_root)
    aggregates = aggregate_runs(runs)
    effects = paired_effects(runs)
    summary_path = tmp_path / "summary.json"
    figure_dir = tmp_path / "figures"
    table_dir = tmp_path / "tables"

    write_analysis_json(summary_path, runs, excluded, aggregates, effects)
    plot_overview(runs, aggregates, figure_dir)
    plot_mechanism(aggregates, effects, figure_dir)
    write_primary_table(aggregates, table_dir / "primary_results.tex")
    write_effect_table(effects, table_dir / "paired_effects.tex")

    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["completed_run_count"] == 48
    assert payload["excluded_run_count"] == 0
    assert len(payload["aggregates"]) == 16
    assert len(payload["paired_effects"]) == 12
    assert {path.name for path in figure_dir.iterdir()} == {
        "mechanism_effects.pdf",
        "mechanism_effects.png",
        "primary_overview.pdf",
        "primary_overview.png",
    }
    assert {path.name for path in table_dir.iterdir()} == {
        "paired_effects.tex",
        "primary_results.tex",
    }
    assert "Direct vLLM" in (table_dir / "primary_results.tex").read_text(
        encoding="utf-8"
    )
