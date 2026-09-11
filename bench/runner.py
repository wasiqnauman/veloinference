"""Open-loop benchmark execution with absolute request arrival targets."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import asdict
from time import monotonic
from typing import Protocol

from bench.client import InferenceClient
from bench.schema import PlannedRequest, RequestResult
from bench.storage import append_jsonl


class RunnerClock(Protocol):
    """Monotonic clock used by scheduling and deterministic tests."""

    def monotonic(self) -> float:
        """Return monotonic time in seconds."""


class SystemRunnerClock:
    """Production clock backed by ``time.monotonic``."""

    def monotonic(self) -> float:
        return monotonic()


class HarnessOverloadError(RuntimeError):
    """Raised when scheduling drift exceeds the configured harness threshold."""


async def execute_planned_request(
    planned: PlannedRequest,
    start_time: float,
    clock: RunnerClock,
    client: InferenceClient,
) -> RequestResult:
    """Send one planned request at its absolute target time."""

    target = start_time + planned.arrival_offset_s
    await asyncio.sleep(max(0.0, target - clock.monotonic()))
    actual = clock.monotonic()
    actual_arrival_s = actual - start_time
    try:
        client_result = await client.infer(planned)
    except Exception as exc:  # noqa: BLE001 - a run must record client failures
        completed_s = clock.monotonic() - start_time
        return _failed_result(planned, actual_arrival_s, completed_s, exc)

    completed_s = clock.monotonic() - start_time
    latency_ms = max(0.0, (completed_s - actual_arrival_s) * 1000)
    return RequestResult(
        schema_version=1,
        experiment_id=planned.experiment_id,
        run_id=planned.run_id,
        request_index=planned.request_index,
        policy=planned.policy,
        model=planned.model,
        workload=planned.workload,
        seed=planned.seed,
        target_arrival_s=planned.arrival_offset_s,
        actual_arrival_s=actual_arrival_s,
        completed_s=completed_s,
        input_tokens=planned.input_tokens,
        output_tokens=client_result.output_tokens,
        batch_id=client_result.batch_id,
        batch_size=client_result.batch_size,
        queue_ms=client_result.queue_ms,
        backend_ms=client_result.backend_ms,
        latency_ms=latency_ms,
        deadline_ms=planned.deadline_ms,
        deadline_met=_deadline_met(planned.deadline_ms, latency_ms),
        status_code=client_result.status_code,
        error_type=None,
    )


async def run_open_loop(
    planned_requests: Sequence[PlannedRequest],
    client: InferenceClient,
    *,
    results_path: object | None = None,
    clock: RunnerClock | None = None,
    start_delay_s: float = 2.0,
    harness_drift_threshold_ms: float = 10.0,
    harness_error_threshold: float = 0.01,
) -> list[RequestResult]:
    """Run every request independently and optionally append each result.

    ``start_delay_s`` defaults to two seconds so the production harness can
    capture its manifest and start GPU monitoring before traffic begins.
    Tests may inject a shorter delay because the scheduling invariant is
    exercised by ``execute_planned_request`` itself.
    """

    if start_delay_s < 0:
        raise ValueError("start_delay_s must be non-negative")
    if harness_drift_threshold_ms < 0:
        raise ValueError("harness_drift_threshold_ms must be non-negative")
    if not 0.0 <= harness_error_threshold <= 1.0:
        raise ValueError("harness_error_threshold must be between 0 and 1")

    run_clock = clock or SystemRunnerClock()
    start_time = run_clock.monotonic() + start_delay_s

    async def execute_and_store(planned: PlannedRequest) -> RequestResult:
        result = await execute_planned_request(planned, start_time, run_clock, client)
        if results_path is not None:
            append_jsonl(results_path, asdict(result))
        return result

    tasks = [
        asyncio.create_task(execute_and_store(planned)) for planned in planned_requests
    ]
    results = await asyncio.gather(*tasks)
    late_count = sum(
        (result.actual_arrival_s - result.target_arrival_s) * 1000
        > harness_drift_threshold_ms
        for result in results
    )
    if results and late_count / len(results) > harness_error_threshold:
        raise HarnessOverloadError(
            f"{late_count}/{len(results)} requests exceeded "
            f"{harness_drift_threshold_ms} ms scheduling drift"
        )
    return list(results)


def _failed_result(
    planned: PlannedRequest,
    actual_arrival_s: float,
    completed_s: float,
    error: Exception,
) -> RequestResult:
    return RequestResult(
        schema_version=1,
        experiment_id=planned.experiment_id,
        run_id=planned.run_id,
        request_index=planned.request_index,
        policy=planned.policy,
        model=planned.model,
        workload=planned.workload,
        seed=planned.seed,
        target_arrival_s=planned.arrival_offset_s,
        actual_arrival_s=actual_arrival_s,
        completed_s=completed_s,
        input_tokens=planned.input_tokens,
        output_tokens=None,
        batch_id=None,
        batch_size=None,
        queue_ms=None,
        backend_ms=None,
        latency_ms=None,
        deadline_ms=planned.deadline_ms,
        deadline_met=None,
        status_code=None,
        error_type=type(error).__name__,
    )


def _deadline_met(deadline_ms: int | None, latency_ms: float) -> bool | None:
    if deadline_ms is None:
        return None
    return latency_ms <= deadline_ms
