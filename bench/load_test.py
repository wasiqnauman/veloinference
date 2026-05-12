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
    mode: str
    requests: int
    concurrency: int
    workload: str
    total_duration_ms: float
    throughput_rps: float
    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    avg_batch_size: float


@dataclass(frozen=True, slots=True)
class Comparison:
    direct: Summary
    batched: Summary
    throughput_gain_pct: float
    avg_latency_delta_ms: float
    p95_latency_delta_ms: float
    avg_batch_size_gain: float


async def send_request(
    client: httpx.AsyncClient,
    endpoint: str,
    prompt: str,
    model: str,
    deadline_ms: int | None,
) -> Sample:
    payload = {"input_text": prompt, "model": model, "deadline_ms": deadline_ms}
    started_at = perf_counter()
    response = await client.post(endpoint, json=payload)
    latency_ms = (perf_counter() - started_at) * 1000
    response.raise_for_status()
    body = response.json()
    return Sample(latency_ms=latency_ms, batch_size=body["batch_size"])


async def run_benchmark(
    mode: str,
    base_url: str,
    requests: int,
    concurrency: int,
    workload_name: str,
    model: str,
    deadline_ms: int | None,
) -> Summary:
    workload = get_workload(workload_name)
    semaphore = asyncio.Semaphore(concurrency)
    endpoint = "/v1/infer/direct" if mode == "direct" else "/v1/infer"
    started_at = perf_counter()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        async def run_one(index: int) -> Sample:
            prompt = workload.prompts[index % len(workload.prompts)]
            async with semaphore:
                return await send_request(client, endpoint, prompt, model, deadline_ms)

        samples = await asyncio.gather(*(run_one(index) for index in range(requests)))

    total_duration_ms = (perf_counter() - started_at) * 1000
    latencies = sorted(sample.latency_ms for sample in samples)
    batch_sizes = [sample.batch_size for sample in samples]

    return Summary(
        mode=mode,
        requests=requests,
        concurrency=concurrency,
        workload=workload.name,
        total_duration_ms=round(total_duration_ms, 2),
        throughput_rps=round(requests / (total_duration_ms / 1000), 2),
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


def compare_summaries(direct: Summary, batched: Summary) -> Comparison:
    throughput_gain_pct = (
        (batched.throughput_rps - direct.throughput_rps) / direct.throughput_rps
    ) * 100

    return Comparison(
        direct=direct,
        batched=batched,
        throughput_gain_pct=round(throughput_gain_pct, 2),
        avg_latency_delta_ms=round(batched.avg_latency_ms - direct.avg_latency_ms, 2),
        p95_latency_delta_ms=round(batched.p95_latency_ms - direct.p95_latency_ms, 2),
        avg_batch_size_gain=round(batched.avg_batch_size - direct.avg_batch_size, 2),
    )


async def run_comparison(
    base_url: str,
    requests: int,
    concurrency: int,
    workload_name: str,
    model: str,
    deadline_ms: int | None,
) -> Comparison:
    direct_summary = await run_benchmark(
        mode="direct",
        base_url=base_url,
        requests=requests,
        concurrency=concurrency,
        workload_name=workload_name,
        model=model,
        deadline_ms=deadline_ms,
    )
    batched_summary = await run_benchmark(
        mode="batched",
        base_url=base_url,
        requests=requests,
        concurrency=concurrency,
        workload_name=workload_name,
        model=model,
        deadline_ms=deadline_ms,
    )
    return compare_summaries(direct_summary, batched_summary)


async def run_sweep(
    base_url: str,
    requests: int,
    concurrencies: list[int],
    workload_name: str,
    model: str,
    deadline_ms: int | None,
) -> list[Comparison]:
    results: list[Comparison] = []
    for concurrency in concurrencies:
        results.append(
            await run_comparison(
                base_url=base_url,
                requests=requests,
                concurrency=concurrency,
                workload_name=workload_name,
                model=model,
                deadline_ms=deadline_ms,
            )
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a simple ADIP load test.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--workload", default="small-prompts")
    parser.add_argument("--model", default="mock")
    parser.add_argument("--deadline-ms", type=int, default=None)
    parser.add_argument("--sweep", default=None)
    parser.add_argument(
        "--mode",
        choices=("direct", "batched", "compare"),
        default="compare",
    )
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def parse_sweep_arg(raw_value: str | None) -> list[int] | None:
    if raw_value is None:
        return None
    return [int(value.strip()) for value in raw_value.split(",") if value.strip()]


def serialize_result(result: Comparison | Summary | list[Comparison]) -> dict | list[dict]:
    if isinstance(result, list):
        return [asdict(item) for item in result]
    return asdict(result)


def main() -> None:
    args = parse_args()
    sweep = parse_sweep_arg(args.sweep)
    if sweep is not None:
        result = asyncio.run(
            run_sweep(
                base_url=args.base_url,
                requests=args.requests,
                concurrencies=sweep,
                workload_name=args.workload,
                model=args.model,
                deadline_ms=args.deadline_ms,
            )
        )
    elif args.mode == "compare":
        result = asyncio.run(
            run_comparison(
                base_url=args.base_url,
                requests=args.requests,
                concurrency=args.concurrency,
                workload_name=args.workload,
                model=args.model,
                deadline_ms=args.deadline_ms,
            )
        )
    else:
        result = asyncio.run(
            run_benchmark(
                mode=args.mode,
                base_url=args.base_url,
                requests=args.requests,
                concurrency=args.concurrency,
                workload_name=args.workload,
                model=args.model,
                deadline_ms=args.deadline_ms,
            )
        )

    serialized = serialize_result(result)
    print(json.dumps(serialized, indent=2))

    if args.output is not None:
        args.output.write_text(json.dumps(serialized, indent=2) + "\n")


if __name__ == "__main__":
    main()
