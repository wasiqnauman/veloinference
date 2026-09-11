"""Deterministic publication figures from benchmark summary records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

from bench.schema import SummaryRecord


def plot_summary(
    summaries: Sequence[SummaryRecord | Mapping[str, object]],
    output_dir: Path,
    *,
    stem: str = "throughput_latency",
) -> tuple[Path, Path]:
    """Write a two-panel throughput/p95-latency figure as PDF and PNG."""

    if not summaries:
        raise ValueError("summaries must not be empty")
    output_dir.mkdir(parents=True, exist_ok=True)
    labels = [str(_field(summary, "run_id")) for summary in summaries]
    throughput = [
        float(_field(summary, "achieved_request_throughput")) for summary in summaries
    ]
    p95_latency = [
        _number_or_nan(_field(summary, "p95_latency_ms")) for summary in summaries
    ]

    figure, axes = plt.subplots(1, 2, figsize=(8, 3.5), constrained_layout=True)
    axes[0].bar(labels, throughput, color="#0072B2")
    axes[0].set_title("Achieved throughput")
    axes[0].set_ylabel("Requests / second")
    axes[0].set_xlabel("Run")
    axes[1].bar(labels, p95_latency, color="#D55E00")
    axes[1].set_title("Tail latency")
    axes[1].set_ylabel("p95 latency (ms)")
    axes[1].set_xlabel("Run")
    for axis in axes:
        axis.tick_params(axis="x", labelrotation=30)

    metadata = {
        "Creator": "ADIP benchmark",
        "Title": stem,
        "CreationDate": None,
        "ModDate": None,
    }
    pdf_path = output_dir / f"{stem}.pdf"
    png_path = output_dir / f"{stem}.png"
    figure.savefig(pdf_path, metadata=metadata)
    figure.savefig(png_path, dpi=160, metadata={"Software": "ADIP benchmark"})
    plt.close(figure)
    return pdf_path, png_path


def _field(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key)
    return getattr(record, key)


def _number_or_nan(value: object) -> float:
    return float(value) if value is not None else float("nan")
