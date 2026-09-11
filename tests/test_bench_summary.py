"""Exact synthetic-fixture tests for summaries and publication plots."""

from __future__ import annotations

import json
from pathlib import Path

from bench.plot import plot_summary
from bench.summarize import summarize_records

FIXTURES = Path(__file__).parent / "fixtures"


def load_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_summary_excludes_warmup_and_keeps_failures() -> None:
    summary = summarize_records(
        load_jsonl(FIXTURES / "request_records.jsonl"),
        load_jsonl(FIXTURES / "gpu_records.jsonl"),
        experiment_id="summary-test",
        run_id="run-1",
        measurement_duration_s=4.0,
        warmup_requests=1,
    )

    assert summary.offered_request_rate == 0.75
    assert summary.achieved_request_throughput == 0.5
    assert summary.achieved_output_token_throughput == 3.0
    assert summary.success_count == 2
    assert summary.failure_count == 1
    assert summary.p50_latency_ms == 20.0
    assert summary.p95_latency_ms == 29.0
    assert summary.p99_latency_ms == 29.8
    assert summary.mean_queue_ms == 4.0
    assert summary.p95_queue_ms == 5.8
    assert summary.mean_backend_ms == 12.5
    assert summary.mean_batch_size == 2.5
    assert summary.slo_attainment_percent == 50.0
    assert summary.mean_gpu_utilization_percent == 30.0
    assert summary.max_vram_used_mb == 800.0
    assert summary.mean_power_draw_w == 55.0
    assert summary.p95_arrival_drift_ms == 1.9


def test_plot_summary_writes_both_publication_formats(tmp_path: Path) -> None:
    summary = summarize_records(
        load_jsonl(FIXTURES / "request_records.jsonl"),
        load_jsonl(FIXTURES / "gpu_records.jsonl"),
        experiment_id="plot-test",
        run_id="run-1",
        measurement_duration_s=4.0,
        warmup_requests=1,
    )

    pdf_path, png_path = plot_summary([summary], tmp_path)

    assert pdf_path.is_file() and pdf_path.stat().st_size > 0
    assert png_path.is_file() and png_path.stat().st_size > 0
