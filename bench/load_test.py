"""Benchmark runner for gateway load tests."""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter

import httpx

from bench.scenarios import get_workload


@dataclass(frozen=True, slots=True)
class Sample:
    latency_ms: float
    batch_size: int


@dataclass(frozen=True, slots=True)
class Summary:
    requests: int
    concurrency: int
    workload: str
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_batch_size: float


async def send_request(
    client: httpx.AsyncClient,
    prompt: str,
    model: str,
    deadline_ms: int | None,
) -> Sample:
    payload = {"input_text": prompt, "model": model, "deadline_ms": deadline_ms}
    started_at = perf_counter()
    response = await client.post("/v1/infer", json=payload)
    latency_ms = (perf_counter() - started_at) * 1000
    response.raise_for_status()
    body = response.json()
    return Sample(latency_ms=latency_ms, batch_size=body["batch_size"])


async def run_benchmark(
    base_url: str,
    requests: int,
    concurrency: int,
    workload_name: str,
    model: str,
    deadline_ms: int | None,
) -> Summary:
    workload = get_workload(workload_name)
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        async def run_one(index: int) -> Sample:
            prompt = workload.prompts[index % len(workload.prompts)]
            async with semaphore:
                return await send_request(client, prompt, model, deadline_ms)

        samples = await asyncio.gather(*(run_one(index) for index in range(requests)))

    latencies = sorted(sample.latency_ms for sample in samples)
    batch_sizes = [sample.batch_size for sample in samples]

    return Summary(
        requests=requests,
        concurrency=concurrency,
        workload=workload.name,
        avg_latency_ms=round(mean(latencies), 2),
        p95_latency_ms=round(percentile(latencies, 95), 2),
        p99_latency_ms=round(percentile(latencies, 99), 2),
        avg_batch_size=round(mean(batch_sizes), 2),
    )


def percentile(values: list[float], percent: int) -> float:
    if not values:
        return 0.0

    index = max(0, min(len(values) - 1, int(len(values) * percent / 100) - 1))
    return values[index]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple ADIP load test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--workload", default="small-prompts")
    parser.add_argument("--model", default="mock")
    parser.add_argument("--deadline-ms", type=int, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = asyncio.run(
        run_benchmark(
            base_url=args.base_url,
            requests=args.requests,
            concurrency=args.concurrency,
            workload_name=args.workload,
            model=args.model,
            deadline_ms=args.deadline_ms,
        )
    )

    print(json.dumps(asdict(summary), indent=2))

    if args.output is not None:
        args.output.write_text(json.dumps(asdict(summary), indent=2) + "\n")


if __name__ == "__main__":
    main()
