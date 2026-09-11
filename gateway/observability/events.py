"""Stable structured event names and JSON-ready event records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

EventName = Literal[
    "request_received",
    "request_enqueued",
    "policy_decision",
    "batch_dispatched",
    "batch_completed",
    "request_completed",
    "request_failed",
]


def utc_timestamp() -> str:
    """Return a compact, timezone-aware event timestamp."""
    return datetime.now(UTC).isoformat(timespec="milliseconds")


@dataclass(frozen=True, slots=True)
class StructuredEvent:
    """One schema-stable event with safe, non-prompt metadata."""

    event: EventName
    request_id: str | None = None
    batch_id: str | None = None
    experiment_id: str | None = None
    timestamp: str = field(default_factory=utc_timestamp)
    data: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.request_id is None and self.batch_id is None:
            raise ValueError("Structured events require a request_id or batch_id")

    def as_dict(self) -> dict[str, object]:
        """Return the JSON-ready event object."""
        payload: dict[str, object] = {
            "timestamp": self.timestamp,
            "event": self.event,
        }
        if self.request_id is not None:
            payload["request_id"] = self.request_id
        if self.batch_id is not None:
            payload["batch_id"] = self.batch_id
        if self.experiment_id is not None:
            payload["experiment_id"] = self.experiment_id
        if self.data:
            payload["data"] = dict(self.data)
        return payload
