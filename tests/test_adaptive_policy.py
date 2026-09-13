"""Deterministic tests for the adaptive batch-closing policy."""

import pytest

from gateway.core.policies.adaptive import AdaptiveWindowPolicy
from gateway.core.policies.base import QueueSnapshot


def make_snapshot(**overrides: object) -> QueueSnapshot:
    values: dict[str, object] = {
        "now": 0.004,
        "oldest_enqueued_at": 0.0,
        "compatible_queue_size": 2,
        "max_batch_size": 8,
        "max_wait_s": 0.010,
        "arrival_rate_per_s": 1000.0,
        "estimated_backend_s": 0.002,
        "earliest_deadline_at": None,
    }
    values.update(overrides)
    return QueueSnapshot(**values)


def test_adaptive_dispatches_full_queue_before_other_rules() -> None:
    decision = AdaptiveWindowPolicy().decide(
        make_snapshot(compatible_queue_size=8, arrival_rate_per_s=0.0)
    )

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "batch_full"


def test_adaptive_bypasses_when_rate_is_zero() -> None:
    decision = AdaptiveWindowPolicy().decide(make_snapshot(arrival_rate_per_s=0.0))

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "low_load_bypass"


def test_adaptive_bypasses_when_expected_companions_are_below_threshold() -> None:
    decision = AdaptiveWindowPolicy(low_load_threshold=1.0).decide(
        make_snapshot(arrival_rate_per_s=10.0, max_wait_s=0.010)
    )

    assert decision.reason == "low_load_bypass"
    assert decision.dispatch_now is True


def test_adaptive_waits_until_estimated_fill_when_rate_supports_it() -> None:
    decision = AdaptiveWindowPolicy(low_load_threshold=0.1).decide(
        make_snapshot(
            compatible_queue_size=2,
            arrival_rate_per_s=1000.0,
            now=0.0,
            oldest_enqueued_at=0.0,
        )
    )

    assert decision.dispatch_now is False
    assert decision.wait_s == pytest.approx(0.006)
    assert decision.reason == "estimated_fill"


def test_adaptive_dispatches_when_deadline_slack_is_exhausted() -> None:
    decision = AdaptiveWindowPolicy().decide(
        make_snapshot(
            now=0.0,
            oldest_enqueued_at=0.0,
            earliest_deadline_at=0.001,
            estimated_backend_s=0.002,
        )
    )

    assert decision.dispatch_now is True
    assert decision.reason == "deadline_slack_exhausted"
