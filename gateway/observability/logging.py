"""JSON-line event logging without prompt or credential leakage."""

from __future__ import annotations

import json
import logging
import re
from typing import Protocol

from gateway.observability.events import EventName, StructuredEvent


class EventLogger(Protocol):
    """Minimal event sink used by service and batcher code."""

    def emit(
        self,
        event: EventName,
        *,
        request_id: str | None = None,
        batch_id: str | None = None,
        experiment_id: str | None = None,
        **data: object,
    ) -> None:
        """Write one structured event."""


def safe_exception_message(error: BaseException) -> str:
    """Return a short message with common credential forms redacted."""
    message = str(error).replace("\n", " ")[:240]
    message = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", message)
    return re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)\S+", r"\1[REDACTED]", message)


class JsonEventLogger:
    """Emit one JSON object per Python logging record."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("adip.events")

    def emit(
        self,
        event: EventName,
        *,
        request_id: str | None = None,
        batch_id: str | None = None,
        experiment_id: str | None = None,
        **data: object,
    ) -> None:
        """Serialize and log an event at INFO without adding prompt data."""
        record = StructuredEvent(
            event=event,
            request_id=request_id,
            batch_id=batch_id,
            experiment_id=experiment_id,
            data=self._safe_data(data),
        )
        self._logger.info(json.dumps(record.as_dict(), sort_keys=True))

    @staticmethod
    def _safe_data(data: dict[str, object]) -> dict[str, object]:
        """Drop prompt and credential fields even if a caller supplies them."""
        unsafe_fragments = (
            "prompt",
            "input_text",
            "api_key",
            "authorization",
        )
        return {
            key: value
            for key, value in data.items()
            if not any(fragment in key.lower() for fragment in unsafe_fragments)
        }


class NullEventLogger:
    """Discard events when research telemetry is explicitly disabled."""

    def emit(
        self,
        event: EventName,
        *,
        request_id: str | None = None,
        batch_id: str | None = None,
        experiment_id: str | None = None,
        **data: object,
    ) -> None:
        """Accept the event shape without producing a log record."""
        return
