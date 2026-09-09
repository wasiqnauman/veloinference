"""Dynamic batching engine."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import Final

from gateway.backends.base import InferenceBackend
from gateway.core.clock import Clock, SystemClock
from gateway.core.models import (
    BatchMetadata,
    BatchKey,
    InferenceRequest,
    InferenceResponse,
    PendingRequest,
)
from gateway.core.policies.base import BatchPolicy, QueueSnapshot
from gateway.core.policies.fixed import FixedWindowPolicy


class QueueOverloadedError(RuntimeError):
    """Raised when the gateway queue is full."""


class BatcherStoppedError(RuntimeError):
    """Raised for requests that cannot complete because the batcher stopped."""


class DynamicBatcher:
    def __init__(
        self,
        backend: InferenceBackend,
        max_batch_size: int,
        max_wait_ms: int,
        queue_max_size: int,
        policy: BatchPolicy | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._backend = backend
        self._max_batch_size = max_batch_size
        self._max_wait_ms = max_wait_ms
        self._policy = policy or FixedWindowPolicy()
        self._clock = clock or SystemClock()
        self._queue: asyncio.Queue[PendingRequest] = asyncio.Queue(maxsize=queue_max_size)
        self._queues: dict[BatchKey, deque[PendingRequest]] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._inflight: list[PendingRequest] = []
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        if self._stopped:
            raise RuntimeError("Batcher has stopped")
        if self._worker_task is None:
            self._started = True
            self._worker_task = asyncio.create_task(self._run(), name="dynamic-batcher")

    async def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            finally:
                self._worker_task = None

        stopped_error: Final = BatcherStoppedError("Batcher stopped")
        for request in self._inflight:
            self._set_exception(request, stopped_error)
        self._inflight.clear()

        while not self._queue.empty():
            request = self._queue.get_nowait()
            self._set_exception(request, stopped_error)

        for pending_queue in self._queues.values():
            while pending_queue:
                self._set_exception(pending_queue.popleft(), stopped_error)
        self._queues.clear()

    async def infer(self, request: InferenceRequest) -> InferenceResponse:
        if not self._started:
            raise RuntimeError("Batcher has not started")
        if self._stopped:
            raise RuntimeError("Batcher is not accepting requests")

        future: asyncio.Future[InferenceResponse] = asyncio.get_running_loop().create_future()
        pending = PendingRequest(
            metadata=BatchMetadata.create(request, clock=self._clock),
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
            if not self._queues:
                first_request = await self._queue.get()
                self._enqueue_pending(first_request)

            key = self._oldest_key()
            batch = await self._collect_batch(key)
            await self._dispatch(batch)

    async def _collect_batch(self, key: BatchKey) -> list[PendingRequest]:
        while True:
            pending_queue = self._queues.get(key)
            if pending_queue is None:
                return []

            self._remove_cancelled(pending_queue)
            if not pending_queue:
                del self._queues[key]
                return []

            decision = self._policy.decide(self._snapshot(key, pending_queue))
            if decision.dispatch_now:
                return self._pop_batch(key)

            try:
                request = await asyncio.wait_for(
                    self._queue.get(), timeout=decision.wait_s
                )
            except asyncio.TimeoutError:
                return self._pop_batch(key)

            self._enqueue_pending(request)

    async def _dispatch(self, batch: list[PendingRequest]) -> None:
        if not batch:
            return

        self._inflight = batch
        try:
            outputs = await self._backend.infer_batch(batch)
            if len(outputs) != len(batch):
                raise RuntimeError("Backend returned an unexpected number of responses")
        except Exception as exc:
            for request in batch:
                self._set_exception(request, exc)
            return
        finally:
            self._inflight = []

        for request, output in zip(batch, outputs, strict=True):
            if request.future is None or request.future.done():
                continue

            request.future.set_result(
                InferenceResponse(
                    request_id=request.metadata.request_id,
                    model=request.metadata.model,
                    output_text=output,
                    batch_size=len(batch),
                )
            )

    def _enqueue_pending(self, request: PendingRequest) -> None:
        if request.future is None or request.future.done():
            return
        self._queues.setdefault(request.metadata.batch_key, deque()).append(request)

    def _oldest_key(self) -> BatchKey:
        return min(
            self._queues,
            key=lambda key: self._queues[key][0].metadata.enqueued_at,
        )

    def _pop_batch(self, key: BatchKey) -> list[PendingRequest]:
        pending_queue = self._queues[key]
        batch: list[PendingRequest] = []
        while pending_queue and len(batch) < self._max_batch_size:
            request = pending_queue.popleft()
            if request.future is None or request.future.done():
                continue
            batch.append(request)
        if not pending_queue:
            del self._queues[key]
        return batch

    @staticmethod
    def _remove_cancelled(pending_queue: deque[PendingRequest]) -> None:
        active = deque(
            request
            for request in pending_queue
            if request.future is not None and not request.future.done()
        )
        pending_queue.clear()
        pending_queue.extend(active)

    def _snapshot(
        self,
        key: BatchKey,
        pending_queue: deque[PendingRequest],
    ) -> QueueSnapshot:
        deadlines = [
            request.metadata.enqueued_at + request.metadata.deadline_ms / 1000
            for request in pending_queue
            if request.metadata.deadline_ms is not None
        ]
        return QueueSnapshot(
            now=self._clock.monotonic(),
            oldest_enqueued_at=pending_queue[0].metadata.enqueued_at,
            compatible_queue_size=len(pending_queue),
            max_batch_size=self._max_batch_size,
            max_wait_s=self._max_wait_ms / 1000,
            arrival_rate_per_s=0.0,
            estimated_backend_s=0.0,
            earliest_deadline_at=min(deadlines) if deadlines else None,
        )

    @staticmethod
    def _set_exception(request: PendingRequest, error: BaseException) -> None:
        if request.future is not None and not request.future.done():
            request.future.set_exception(error)
