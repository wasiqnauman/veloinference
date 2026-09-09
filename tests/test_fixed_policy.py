"""Deterministic tests for the fixed-window policy."""

import pytest

from gateway.core.policies.base import QueueSnapshot
from gateway.core.policies.fixed import FixedWindowPolicy


def make_snapshot(**overrides: object) -> QueueSnapshot:
    values: dict[str, object] = {
        "now": 1.0,
        "oldest_enqueued_at": 0.0,
        "compatible_queue_size": 1,
        "max_batch_size": 8,
        "max_wait_s": 0.010,
        "arrival_rate_per_s": 100.0,
        "estimated_backend_s": 0.005,
        "earliest_deadline_at": None,
    }
    values.update(overrides)
    return QueueSnapshot(**values)


def test_dispatches_when_batch_is_full() -> None:
    decision = FixedWindowPolicy().decide(
        make_snapshot(compatible_queue_size=8, now=0.001, oldest_enqueued_at=0.0)
    )

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "batch_full"


def test_dispatches_when_wait_window_has_elapsed() -> None:
    decision = FixedWindowPolicy().decide(
        make_snapshot(now=0.010, oldest_enqueued_at=0.0)
    )

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "wait_window_elapsed"


def test_dispatches_before_wait_consumes_deadline_service_slack() -> None:
    decision = FixedWindowPolicy().decide(
        make_snapshot(
            now=0.0,
            oldest_enqueued_at=0.0,
            max_wait_s=0.010,
            estimated_backend_s=0.004,
            earliest_deadline_at=0.012,
        )
    )

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "deadline_slack_exhausted"


def test_returns_remaining_configured_wait_when_safe() -> None:
    decision = FixedWindowPolicy().decide(
        make_snapshot(now=0.004, oldest_enqueued_at=0.0)
    )

    assert decision.dispatch_now is False
    assert decision.wait_s == pytest.approx(0.006)
    assert decision.reason == "configured_wait"


def test_decision_never_returns_negative_wait() -> None:
    decision = FixedWindowPolicy().decide(
        make_snapshot(now=0.0, oldest_enqueued_at=1.0, max_wait_s=-1.0)
    )

    assert decision.dispatch_now is True
    assert decision.wait_s == 0.0
    assert decision.reason == "wait_window_elapsed"
