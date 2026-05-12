"""Dynamic batching engine."""

import asyncio
from collections import deque

from gateway.backends.base import InferenceBackend
from gateway.core.models import (
    BatchMetadata,
    InferenceRequest,
    InferenceResponse,
    PendingRequest,
)
from gateway.core.scheduler import remaining_wait_time, request_has_expired


class QueueOverloadedError(RuntimeError):
    """Raised when the gateway queue is full."""


class DynamicBatcher:
    def __init__(
        self,
        backend: InferenceBackend,
        max_batch_size: int,
        max_wait_ms: int,
        queue_max_size: int,
    ) -> None:
        self._backend = backend
        self._max_batch_size = max_batch_size
        self._max_wait_ms = max_wait_ms
        self._queue: asyncio.Queue[PendingRequest] = asyncio.Queue(maxsize=queue_max_size)
        self._pending: deque[PendingRequest] = deque()
        self._worker_task: asyncio.Task[None] | None = None
        self._stopped = False

    async def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._run(), name="dynamic-batcher")

    async def stop(self) -> None:
        self._stopped = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None

        while self._pending:
            request = self._pending.popleft()
            if not request.future.done():
                request.future.set_exception(RuntimeError("Batcher stopped"))

        while not self._queue.empty():
            request = self._queue.get_nowait()
            if not request.future.done():
                request.future.set_exception(RuntimeError("Batcher stopped"))

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        if self._stopped:
            raise RuntimeError("Batcher is not accepting requests")

        future: asyncio.Future[InferenceResponse] = asyncio.get_running_loop().create_future()
        pending = PendingRequest(
            metadata=BatchMetadata.create(request),
            payload=request,
            future=future,
        )

        try:
            self._queue.put_nowait(pending)
        except asyncio.QueueFull as exc:
            raise QueueOverloadedError("Gateway queue is full") from exc

        return await future

    async def _run(self) -> None:
        while True:
            if not self._pending:
                first_request = await self._queue.get()
                self._pending.append(first_request)

            batch = await self._collect_batch()
            await self._dispatch(batch)

    async def _collect_batch(self) -> list[PendingRequest]:
        while len(self._pending) < self._max_batch_size:
            while len(self._pending) < self._max_batch_size:
                try:
                    request = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    self._pending.append(request)

            if len(self._pending) >= self._max_batch_size:
                break

            first_request = self._pending[0]
            timeout = remaining_wait_time(first_request, self._max_wait_ms)
            if timeout <= 0:
                break

            try:
                request = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            except asyncio.TimeoutError:
                break

            self._pending.append(request)
            if request_has_expired(first_request):
                break

        batch: list[PendingRequest] = []
        while self._pending and len(batch) < self._max_batch_size:
            batch.append(self._pending.popleft())
        return batch

    async def _dispatch(self, batch: list[PendingRequest]) -> None:
        if not batch:
            return

        try:
            outputs = await self._backend.infer_batch(batch)
            if len(outputs) != len(batch):
                raise RuntimeError("Backend returned an unexpected number of responses")
        except Exception as exc:
            for request in batch:
                if not request.future.done():
                    request.future.set_exception(exc)
            return

        for request, output in zip(batch, outputs, strict=True):
            if request.future.done():
                continue

            request.future.set_result(
                InferenceResponse(
                    request_id=request.metadata.request_id,
                    model=request.metadata.model,
                    output_text=output,
                    batch_size=len(batch),
                )
            )
