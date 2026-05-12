"""Utilities for plotting benchmark output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_summary(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def render_markdown_table(comparisons: list[dict[str, Any]]) -> str:
    header = (
        "| Concurrency | Direct Throughput (req/s) | Batched Throughput (req/s) | "
        "Throughput Gain | Direct p95 (ms) | Batched p95 (ms) | Avg Batch Size |\n"
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"
    )
    rows = []
    for comparison in comparisons:
        direct = comparison["direct"]
        batched = comparison["batched"]
        rows.append(
            "| {concurrency} | {direct_rps:.2f} | {batched_rps:.2f} | {gain:.2f}% | "
            "{direct_p95:.2f} | {batched_p95:.2f} | {batch_size:.2f} |".format(
                concurrency=direct["concurrency"],
                direct_rps=direct["throughput_rps"],
                batched_rps=batched["throughput_rps"],
                gain=comparison["throughput_gain_pct"],
                direct_p95=direct["p95_latency_ms"],
                batched_p95=batched["p95_latency_ms"],
                batch_size=batched["avg_batch_size"],
            )
        )
    return "\n".join([header, *rows])


def build_layman_story(comparisons: list[dict[str, Any]]) -> str:
    if not comparisons:
        return ""

    strongest = max(comparisons, key=lambda item: item["throughput_gain_pct"])
    direct = strongest["direct"]
    batched = strongest["batched"]

    return (
        "Think of the direct path like sending one passenger per taxi. "
        "The batched path waits a few milliseconds, fills the car, and sends several "
        "passengers together. In the strongest run at concurrency "
        f"{direct['concurrency']}, ADIP increased throughput from "
        f"{direct['throughput_rps']:.2f} to {batched['throughput_rps']:.2f} requests per second "
        f"while reducing average latency from {direct['avg_latency_ms']:.2f} ms to "
        f"{batched['avg_latency_ms']:.2f} ms. The gateway was able to process nearly "
        f"{batched['avg_batch_size']:.0f} requests at a time on average, which is why the "
        "backend spent less time paying the same fixed overhead again and again."
    )
