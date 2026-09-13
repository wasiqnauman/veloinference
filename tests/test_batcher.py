"""Batcher tests."""

import asyncio
from collections.abc import Sequence

import pytest

from gateway.backends.base import InferenceBackend
from gateway.backends.mock import MockBackend
from gateway.core.batcher import BatcherStoppedError, DynamicBatcher
from gateway.core.models import BackendOutput, InferenceRequest, PendingRequest


class RecordingBackend(InferenceBackend):
    def __init__(self) -> None:
        self.batch_keys: list[list[object]] = []

    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[str]:
        self.batch_keys.append([request.metadata.batch_key for request in requests])
        return [BackendOutput(output_text=request.payload.input_text) for request in requests]


class BlockingBackend(InferenceBackend):
    def __init__(self) -> None:
        self.started = asyncio.Event()

    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[str]:
        self.started.set()
        await asyncio.Future()
        return [BackendOutput(output_text=request.payload.input_text) for request in requests]


class SlowRecordingBackend(RecordingBackend):
    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[BackendOutput]:
        self.batch_keys.append([request.metadata.batch_key for request in requests])
        await asyncio.sleep(0.75)
        return [BackendOutput(output_text=request.payload.input_text) for request in requests]


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


@pytest.mark.asyncio
async def test_queued_requests_share_a_batch_after_slow_backend_returns() -> None:
    backend = SlowRecordingBackend()
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=8,
        max_wait_ms=1,
        queue_max_size=32,
    )
    await batcher.start()

    async def send_after(delay_s: float, text: str):
        await asyncio.sleep(delay_s)
        return await batcher.infer(InferenceRequest(input_text=text))

    try:
        responses = await asyncio.gather(
            *(send_after(delay, f"request-{index}") for index, delay in enumerate((0.0, 0.25, 0.5, 0.75)))
        )
    finally:
        await batcher.stop()

    assert [response.batch_size for response in responses] == [1, 3, 3, 3]
    assert [len(batch) for batch in backend.batch_keys] == [1, 3]


@pytest.mark.asyncio
async def test_incompatible_requests_never_share_a_batch() -> None:
    backend = RecordingBackend()
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=8,
        max_wait_ms=1,
        queue_max_size=32,
    )
    await batcher.start()

    try:
        first, second = await asyncio.gather(
            batcher.infer(InferenceRequest(input_text="first", model="model-a")),
            batcher.infer(InferenceRequest(input_text="second", model="model-b")),
        )
    finally:
        await batcher.stop()

    assert first.output_text == "first"
    assert second.output_text == "second"
    assert [len(batch) for batch in backend.batch_keys] == [1, 1]


@pytest.mark.asyncio
async def test_start_and_stop_are_idempotent_with_clear_lifecycle_errors() -> None:
    batcher = DynamicBatcher(
        backend=MockBackend(base_latency_ms=0, per_item_latency_ms=0),
        max_batch_size=1,
        max_wait_ms=1,
        queue_max_size=4,
    )

    with pytest.raises(RuntimeError, match="not started"):
        await batcher.infer(InferenceRequest(input_text="before-start"))

    await batcher.start()
    await batcher.start()
    response = await batcher.infer(InferenceRequest(input_text="ready"))
    assert response.output_text == "mock:ready|batch=1"

    await batcher.stop()
    await batcher.stop()
    with pytest.raises(RuntimeError, match="not accepting"):
        await batcher.infer(InferenceRequest(input_text="after-stop"))


@pytest.mark.asyncio
async def test_stop_rejects_requests_while_backend_is_in_flight() -> None:
    backend = BlockingBackend()
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=1,
        max_wait_ms=1,
        queue_max_size=4,
    )
    await batcher.start()
    request_task = asyncio.create_task(
        batcher.infer(InferenceRequest(input_text="in-flight"))
    )

    await backend.started.wait()
    await batcher.stop()

    with pytest.raises(BatcherStoppedError, match="Batcher stopped"):
        await request_task
