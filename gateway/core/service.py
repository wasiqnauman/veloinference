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

GatewayMode = Literal["pass_through", "batched"]


class InferenceService:
    """Execute requests through the configured pass-through or batch path."""

    def __init__(
        self,
        backend: InferenceBackend,
        batcher: DynamicBatcher,
        mode: GatewayMode,
        clock: Clock,
    ) -> None:
        if mode not in ("pass_through", "batched"):
            raise ValueError(f"Unsupported gateway mode: {mode}")
        self._backend = backend
        self._batcher = batcher
        self._mode = mode
        self._clock = clock

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        """Execute one validated request and return normalized response data."""
        if self._mode == "batched":
            return await self._batcher.infer(request)

        metadata = BatchMetadata.create(request, clock=self._clock)
        pending = PendingRequest(metadata=metadata, payload=request, future=None)
        backend_started = self._clock.monotonic()
        output = await self._backend.infer_one(pending)
        completed_at = self._clock.monotonic()
        deadline_met = self._deadline_met(metadata, completed_at)
        backend_ms = max(0.0, (completed_at - backend_started) * 1000)
        total_ms = max(0.0, (completed_at - metadata.enqueued_at) * 1000)

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
