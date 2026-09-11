"""Structured event and in-process metrics tests."""

import json
import logging

import pytest

from gateway.core.models import BatchKey
from gateway.observability.events import StructuredEvent
from gateway.observability.logging import JsonEventLogger, safe_exception_message
from gateway.observability.metrics import MetricsRegistry


def test_structured_event_is_json_ready_and_requires_an_identifier() -> None:
    """Every event has a timestamp and at least one correlation identifier."""
    event = StructuredEvent(
        event="request_received",
        request_id="request-1",
        experiment_id="experiment-1",
        data={"model": "mock"},
    )

    payload = event.as_dict()

    assert payload["event"] == "request_received"
    assert payload["request_id"] == "request-1"
    assert payload["experiment_id"] == "experiment-1"
    assert payload["data"] == {"model": "mock"}
    assert "timestamp" in payload
    with pytest.raises(ValueError, match="request_id or batch_id"):
        StructuredEvent(event="batch_completed")


def test_json_logger_emits_one_record_without_prompt_text(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("adip.test.events")
    event_logger = JsonEventLogger(logger)

    with caplog.at_level(logging.INFO, logger="adip.test.events"):
        event_logger.emit(
            "request_received",
            request_id="request-1",
            model="mock",
            input_text="must-not-be-logged",
        )

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "request_received"
    assert payload["request_id"] == "request-1"
    assert "must-not-be-logged" not in caplog.records[-1].message


def test_metrics_registry_tracks_counts_batch_sizes_and_ewmas() -> None:
    metrics = MetricsRegistry(ewma_alpha=0.5)
    key = BatchKey(model="mock", max_tokens=32, temperature=0.0)

    metrics.record_received(key, 0.0)
    metrics.record_received(key, 1.0)
    metrics.record_batch(2)
    metrics.record_backend_latency(0.2)
    metrics.record_completed()
    metrics.record_failed()
    metrics.record_rejected()

    snapshot = metrics.snapshot()

    assert snapshot.received_requests == 2
    assert snapshot.completed_requests == 1
    assert snapshot.failed_requests == 1
    assert snapshot.rejected_requests == 1
    assert snapshot.batches == 1
    assert snapshot.batch_sizes == (2,)
    assert snapshot.backend_latency_ewma_s == 0.2
    assert snapshot.arrival_rate_ewma_per_s["mock|32|0.0"] == 1.0


def test_exception_message_redacts_common_credentials() -> None:
    message = safe_exception_message(
        RuntimeError("Authorization Bearer secret api_key=private-value")
    )

    assert "secret" not in message
    assert "private-value" not in message
    assert "[REDACTED]" in message
