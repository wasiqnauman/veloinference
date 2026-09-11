"""Tests for deterministic EXP-001 request planning."""

from __future__ import annotations

from pathlib import Path

from bench.calibration import build_calibration_requests
from bench.config import load_experiment_config
from bench.prompts import WhitespaceTokenCounter, build_prompt_set

ROOT = Path(__file__).resolve().parents[1]


def test_calibration_requests_are_preplanned_at_requested_rate() -> None:
    config = load_experiment_config(ROOT / "configs" / "experiments" / "mock_smoke.toml")
    prompts = build_prompt_set(
        WhitespaceTokenCounter(),
        config.workload.prompt_buckets,
        prompts_per_bucket=1,
        seed=1729,
    )

    requests = build_calibration_requests(config, 2.0, "rate-2", prompts)

    assert len(requests) == 2
    assert [request.arrival_offset_s for request in requests] == [0.0, 0.5]
    assert all(request.run_id == "rate-2" for request in requests)
