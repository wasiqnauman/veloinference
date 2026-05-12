"""Mock backend for local development and testing."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from gateway.backends.base import InferenceBackend
from gateway.core.models import PendingRequest


class MockBackend(InferenceBackend):
    def __init__(self, base_latency_ms: int, per_item_latency_ms: int) -> None:
        self._base_latency_ms = base_latency_ms
        self._per_item_latency_ms = per_item_latency_ms
        self._device_lock = asyncio.Lock()

    async def infer_one(self, request: PendingRequest) -> str:
        async with self._device_lock:
            await asyncio.sleep((self._base_latency_ms + self._per_item_latency_ms) / 1000)
        return f"mock:{request.payload.input_text.strip()}|batch=1"

    async def infer_batch(self, requests: Sequence[PendingRequest]) -> list[str]:
        batch_size = len(requests)
        delay_ms = self._base_latency_ms + self._per_item_latency_ms * batch_size
        async with self._device_lock:
            await asyncio.sleep(delay_ms / 1000)

        return [
            f"mock:{request.payload.input_text.strip()}|batch={batch_size}"
            for request in requests
        ]
