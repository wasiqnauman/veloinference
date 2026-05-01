"""Batcher tests."""

import asyncio

import pytest

from gateway.backends.mock import MockBackend
from gateway.core.batcher import DynamicBatcher
from gateway.core.models import InferenceRequest


@pytest.mark.asyncio
async def test_concurrent_requests_share_a_batch() -> None:
    batcher = DynamicBatcher(
        backend=MockBackend(base_latency_ms=1, per_item_latency_ms=0),
        max_batch_size=8,
        max_wait_ms=25,
        queue_max_size=32,
    )
    await batcher.start()

    try:
        first, second = await asyncio.gather(
            batcher.infer(InferenceRequest(input_text="first")),
            batcher.infer(InferenceRequest(input_text="second")),
        )
    finally:
        await batcher.stop()

    assert first.batch_size == 2
    assert second.batch_size == 2
    assert first.output_text == "mock:first|batch=2"
    assert second.output_text == "mock:second|batch=2"
