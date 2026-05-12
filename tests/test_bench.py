"""Benchmark utility tests."""

from bench.load_test import Summary, compare_summaries, parse_sweep_arg, percentile
from bench.plot_results import build_layman_story, render_markdown_table
from bench.scenarios import get_workload


def test_get_workload_returns_expected_scenario() -> None:
    workload = get_workload("small-prompts")

    assert workload.name == "small-prompts"
    assert workload.prompts


def test_percentile_uses_sorted_samples() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert percentile(values, 95) == 4.0


def test_compare_summaries_reports_batching_gain() -> None:
    direct = Summary(
        mode="direct",
        requests=200,
        concurrency=32,
        workload="small-prompts",
        total_duration_ms=4000.0,
        throughput_rps=50.0,
        avg_latency_ms=20.0,
        p95_latency_ms=24.0,
        p99_latency_ms=28.0,
        avg_batch_size=1.0,
    )
    batched = Summary(
        mode="batched",
        requests=200,
        concurrency=32,
        workload="small-prompts",
        total_duration_ms=2000.0,
        throughput_rps=100.0,
        avg_latency_ms=10.0,
        p95_latency_ms=14.0,
        p99_latency_ms=17.0,
        avg_batch_size=4.0,
    )

    comparison = compare_summaries(direct, batched)

    assert comparison.throughput_gain_pct == 100.0
    assert comparison.avg_latency_delta_ms == -10.0
    assert comparison.p95_latency_delta_ms == -10.0
    assert comparison.avg_batch_size_gain == 3.0


def test_parse_sweep_arg_returns_concurrency_list() -> None:
    assert parse_sweep_arg("8, 16,32") == [8, 16, 32]


def test_report_helpers_render_readable_output() -> None:
    comparison = {
        "direct": {
            "concurrency": 64,
            "throughput_rps": 100.0,
            "avg_latency_ms": 1200.0,
            "p95_latency_ms": 1300.0,
        },
        "batched": {
            "concurrency": 64,
            "throughput_rps": 320.0,
            "avg_latency_ms": 370.0,
            "p95_latency_ms": 410.0,
            "avg_batch_size": 8.0,
        },
        "throughput_gain_pct": 220.0,
    }

    table = render_markdown_table([comparison])
    story = build_layman_story([comparison])

    assert "Concurrency" in table
    assert "220.00%" in table
    assert "taxi" in story
    assert "320.00" in story
