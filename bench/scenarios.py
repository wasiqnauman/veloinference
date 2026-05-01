"""Benchmark workload scenarios."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Workload:
    name: str
    prompts: tuple[str, ...]


SMALL_PROMPTS = Workload(
    name="small-prompts",
    prompts=(
        "What is dynamic batching?",
        "Summarize this request.",
        "Classify this input.",
        "Translate this sentence.",
    ),
)

MIXED_PROMPTS = Workload(
    name="mixed-prompts",
    prompts=(
        "One short prompt.",
        "Summarize the benefits of deadline-aware batching in two sentences.",
        "Explain how a model gateway can improve utilization under bursty traffic.",
        (
            "Describe the tradeoff between throughput and tail latency in an inference "
            "proxy that batches requests over a short window."
        ),
    ),
)

WORKLOADS = {
    SMALL_PROMPTS.name: SMALL_PROMPTS,
    MIXED_PROMPTS.name: MIXED_PROMPTS,
}


def get_workload(name: str) -> Workload:
    try:
        return WORKLOADS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown workload: {name}") from exc
