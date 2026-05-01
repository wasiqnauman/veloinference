"""Mock backend tests."""

import asyncio

import pytest

from gateway.backends.mock import MockBackend
from gateway.core.models import BatchMetadata, InferenceRequest, PendingRequest


@pytest.mark.asyncio
async def test_mock_backend_preserves_order() -> None:
    backend = MockBackend(base_latency_ms=0, per_item_latency_ms=0)
    loop = asyncio.get_running_loop()
    requests = [
        PendingRequest(
            metadata=BatchMetadata.create(InferenceRequest(input_text="one")),
            payload=InferenceRequest(input_text="one"),
            future=loop.create_future(),
        ),
        PendingRequest(
            metadata=BatchMetadata.create(InferenceRequest(input_text="two")),
            payload=InferenceRequest(input_text="two"),
            future=loop.create_future(),
        ),
    ]

    outputs = await backend.infer_batch(requests)

    assert outputs == ["mock:one|batch=2", "mock:two|batch=2"]
