"""Inference service orchestration."""

from __future__ import annotations

import asyncio

from gateway.backends.base import InferenceBackend
from gateway.core.batcher import DynamicBatcher
from gateway.core.models import BatchMetadata, InferenceRequest, InferenceResponse, PendingRequest


class InferenceService:
    def __init__(self, backend: InferenceBackend, batcher: DynamicBatcher) -> None:
        self._backend = backend
        self._batcher = batcher

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        return await self._batcher.infer(request)

    async def infer_direct(self, request: InferenceRequest) -> InferenceResponse:
        future: asyncio.Future[InferenceResponse] = asyncio.get_running_loop().create_future()
        pending = PendingRequest(
            metadata=BatchMetadata.create(request),
            payload=request,
            future=future,
        )
        output = await self._backend.infer_one(pending)
        return InferenceResponse(
            request_id=pending.metadata.request_id,
            model=pending.metadata.model,
            output_text=output,
            batch_size=1,
        )
