"""Benchmark utility tests."""

from bench.load_test import percentile
from bench.scenarios import get_workload


def test_get_workload_returns_expected_scenario() -> None:
    workload = get_workload("small-prompts")

    assert workload.name == "small-prompts"
    assert workload.prompts


def test_percentile_uses_sorted_samples() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert percentile(values, 95) == 4.0
