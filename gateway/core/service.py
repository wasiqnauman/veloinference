"""Mode-aware inference service used by the HTTP routes."""

from __future__ import annotations

from typing import Literal

from gateway.backends.base import InferenceBackend
from gateway.core.batcher import DynamicBatcher
from gateway.core.clock import Clock
from gateway.core.models import (
    BatchMetadata,
    InferenceRequest,
    InferenceResponse,
    PendingRequest,
)
from gateway.observability.logging import (
    EventLogger,
    JsonEventLogger,
    safe_exception_message,
)
from gateway.observability.metrics import MetricsRegistry

GatewayMode = Literal["pass_through", "batched"]


class InferenceService:
    """Execute requests through the configured pass-through or batch path."""

    def __init__(
        self,
        backend: InferenceBackend,
        batcher: DynamicBatcher,
        mode: GatewayMode,
        clock: Clock,
        event_logger: EventLogger | None = None,
        metrics: MetricsRegistry | None = None,
    ) -> None:
        if mode not in ("pass_through", "batched"):
            raise ValueError(f"Unsupported gateway mode: {mode}")
        self._backend = backend
        self._batcher = batcher
        self._mode = mode
        self._clock = clock
        self._event_logger = event_logger or JsonEventLogger()
        self._metrics = metrics or MetricsRegistry()

    async def infer(
        self,
        request: InferenceRequest,
        experiment_id: str | None = None,
    ) -> InferenceResponse:
        """Execute one validated request and return normalized response data."""
        received_at = self._clock.monotonic()
        metadata = BatchMetadata.create(
            request,
            clock=self._clock,
            experiment_id=experiment_id,
        )
        self._metrics.record_received(metadata.batch_key, received_at)
        self._event_logger.emit(
            "request_received",
            request_id=metadata.request_id,
            experiment_id=experiment_id,
            model=request.model,
        )
        if self._mode == "batched":
            return await self._batcher.infer(request, experiment_id=experiment_id)

        pending = PendingRequest(metadata=metadata, payload=request, future=None)
        self._event_logger.emit(
            "request_enqueued",
            request_id=metadata.request_id,
            experiment_id=experiment_id,
            model=request.model,
            mode="pass_through",
        )
        backend_started = self._clock.monotonic()
        try:
            output = await self._backend.infer_one(pending)
        except Exception as exc:
            self._metrics.record_failed()
            self._event_logger.emit(
                "request_failed",
                request_id=metadata.request_id,
                experiment_id=experiment_id,
                error_type=type(exc).__name__,
                safe_message=safe_exception_message(exc),
            )
            raise
        completed_at = self._clock.monotonic()
        deadline_met = self._deadline_met(metadata, completed_at)
        backend_ms = max(0.0, (completed_at - backend_started) * 1000)
        total_ms = max(0.0, (completed_at - metadata.enqueued_at) * 1000)
        self._metrics.record_backend_latency(completed_at - backend_started)
        self._metrics.record_completed()
        self._event_logger.emit(
            "request_completed",
            request_id=metadata.request_id,
            experiment_id=experiment_id,
            batch_size=1,
            queue_ms=0.0,
            backend_ms=backend_ms,
            total_ms=total_ms,
            deadline_met=deadline_met,
        )

        return InferenceResponse(
            request_id=metadata.request_id,
            model=metadata.model,
            output_text=output.output_text,
            output_tokens=output.output_tokens,
            batch_size=1,
            batch_id=None,
            queue_ms=0.0,
            backend_ms=backend_ms,
            total_ms=total_ms,
            deadline_met=deadline_met,
        )

    @staticmethod
    def _deadline_met(metadata: BatchMetadata, completed_at: float) -> bool | None:
        if metadata.deadline_ms is None:
            return None
        deadline_at = metadata.enqueued_at + metadata.deadline_ms / 1000
        return completed_at <= deadline_at
