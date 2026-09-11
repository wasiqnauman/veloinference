"""Deterministic open-loop arrival schedule generators."""

from __future__ import annotations

import math
import random


def constant_arrivals(rate_per_s: float, duration_s: float) -> list[float]:
    """Return deterministic equally spaced offsets beginning at zero."""

    _validate_rate_and_duration(rate_per_s, duration_s)
    count = max(1, math.ceil(rate_per_s * duration_s - 1e-12))
    return [offset for offset in (index / rate_per_s for index in range(count)) if offset < duration_s]


def poisson_arrivals(rate_per_s: float, duration_s: float, seed: int) -> list[float]:
    """Return offsets generated from exponential inter-arrival times."""

    _validate_rate_and_duration(rate_per_s, duration_s)
    generator = random.Random(seed)
    offsets: list[float] = []
    offset = 0.0
    while True:
        offset += generator.expovariate(rate_per_s)
        if offset >= duration_s:
            return offsets
        offsets.append(offset)


def bursty_arrivals(
    low_rate_per_s: float,
    high_rate_per_s: float,
    burst_probability: float,
    interval_s: float,
    duration_s: float,
    seed: int,
) -> list[float]:
    """Choose a rate per interval and generate Poisson arrivals within it."""

    _validate_rate_and_duration(low_rate_per_s, duration_s)
    _validate_rate_and_duration(high_rate_per_s, duration_s)
    if low_rate_per_s > high_rate_per_s:
        raise ValueError("low_rate_per_s cannot exceed high_rate_per_s")
    if not math.isfinite(burst_probability) or not 0.0 <= burst_probability <= 1.0:
        raise ValueError("burst_probability must be finite and between 0 and 1")
    if not math.isfinite(interval_s) or interval_s <= 0:
        raise ValueError("interval_s must be finite and greater than 0")

    generator = random.Random(seed)
    offsets: list[float] = []
    interval_start = 0.0
    while interval_start < duration_s:
        interval_end = min(duration_s, interval_start + interval_s)
        rate = (
            high_rate_per_s
            if generator.random() < burst_probability
            else low_rate_per_s
        )
        local_offset = 0.0
        while True:
            local_offset += generator.expovariate(rate)
            if interval_start + local_offset >= interval_end:
                break
            offsets.append(interval_start + local_offset)
        interval_start = interval_end
    return offsets


def _validate_rate_and_duration(rate_per_s: float, duration_s: float) -> None:
    if not math.isfinite(rate_per_s) or rate_per_s <= 0:
        raise ValueError("rate_per_s must be finite and greater than 0")
    if not math.isfinite(duration_s) or duration_s <= 0:
        raise ValueError("duration_s must be finite and greater than 0")
