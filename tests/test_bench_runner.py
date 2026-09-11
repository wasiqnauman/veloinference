"""Tests for open-loop scheduling and result persistence."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from bench.client import ClientResult
from bench.runner import execute_planned_request, run_open_loop
from bench.schema import PlannedRequest
from bench.storage import append_jsonl, write_json_atomic


def planned(index: int, arrival_offset_s: float = 0.0) -> PlannedRequest:
    return PlannedRequest(
        schema_version=1,
        experiment_id="runner-test",
        run_id="run-1",
        request_index=index,
        policy="fixed",
        model="mock",
        workload="short",
        seed=1729,
        arrival_offset_s=arrival_offset_s,
        prompt=f"prompt-{index}",
        input_tokens=1,
        max_tokens=8,
        temperature=0.0,
        deadline_ms=100,
    )


class SlowFirstClient:
    def __init__(self) -> None:
        self.arrivals: dict[int, float] = {}

    async def infer(self, request: PlannedRequest) -> ClientResult:
        self.arrivals[request.request_index] = asyncio.get_running_loop().time()
        await asyncio.sleep(0.05 if request.request_index == 0 else 0.001)
        return ClientResult(
            output_text="ok",
            output_tokens=2,
            batch_id=f"batch-{request.request_index}",
            batch_size=1,
            queue_ms=0.5,
            backend_ms=1.0,
            status_code=200,
        )


@pytest.mark.asyncio
async def test_later_target_arrival_is_not_blocked_by_slow_prior_request() -> None:
    client = SlowFirstClient()
    start_time = asyncio.get_running_loop().time() + 0.02

    results = await asyncio.gather(
        execute_planned_request(planned(0), start_time, client_clock(), client),
        execute_planned_request(planned(1, 0.005), start_time, client_clock(), client),
    )

    assert results[1].actual_arrival_s < results[0].completed_s
    assert client.arrivals[1] < client.arrivals[0] + 0.05


@pytest.mark.asyncio
async def test_runner_appends_one_valid_json_record_per_completion(tmp_path: Path) -> None:
    output = tmp_path / "run" / "requests.jsonl"
    results = await run_open_loop(
        [planned(0), planned(1, 0.005)],
        SlowFirstClient(),
        results_path=output,
        start_delay_s=0.01,
        harness_drift_threshold_ms=100.0,
    )

    records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(results) == 2
    assert len(records) == 2
    assert {record["request_index"] for record in records} == {0, 1}
    assert all(record["status_code"] == 200 for record in records)


def client_clock() -> object:
    """Return a clock compatible with the runner using the asyncio loop clock."""

    class LoopClock:
        def monotonic(self) -> float:
            return asyncio.get_running_loop().time()

    return LoopClock()


def test_jsonl_and_atomic_writers_create_parent_and_replace(tmp_path: Path) -> None:
    jsonl = tmp_path / "nested" / "records.jsonl"
    append_jsonl(jsonl, {"request_index": 0, "ok": True})
    append_jsonl(jsonl, {"request_index": 1, "ok": True})
    assert [json.loads(line)["request_index"] for line in jsonl.read_text().splitlines()] == [0, 1]

    manifest = tmp_path / "nested" / "manifest.json"
    write_json_atomic(manifest, {"version": 1, "status": "complete"})
    write_json_atomic(manifest, {"version": 2, "status": "complete"})
    assert json.loads(manifest.read_text())["version"] == 2
    assert not list(manifest.parent.glob(".manifest.json.tmp-*"))
