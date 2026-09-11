"""Tests for deterministic arrival schedules and prompt buckets."""

from __future__ import annotations

from pathlib import Path

import pytest

from bench.arrivals import bursty_arrivals, constant_arrivals, poisson_arrivals
from bench.prompts import (
    PromptGenerationError,
    WhitespaceTokenCounter,
    build_prompt_set,
    validate_prompt_counts,
)
from bench.schema import PromptBucket


def test_constant_arrivals_start_at_zero_and_stay_in_window() -> None:
    offsets = constant_arrivals(rate_per_s=4.0, duration_s=1.0)

    assert offsets == [0.0, 0.25, 0.5, 0.75]
    assert all(0.0 <= offset < 1.0 for offset in offsets)


def test_stochastic_arrivals_are_seed_deterministic_and_sorted() -> None:
    poisson_a = poisson_arrivals(10.0, 2.0, seed=1729)
    poisson_b = poisson_arrivals(10.0, 2.0, seed=1729)
    bursty_a = bursty_arrivals(2.0, 20.0, 0.4, 0.5, 2.0, seed=1729)
    bursty_b = bursty_arrivals(2.0, 20.0, 0.4, 0.5, 2.0, seed=1729)

    assert poisson_a == poisson_b
    assert bursty_a == bursty_b
    assert poisson_a == sorted(poisson_a)
    assert bursty_a == sorted(bursty_a)
    assert all(0.0 <= offset < 2.0 for offset in poisson_a + bursty_a)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: constant_arrivals(0.0, 1.0),
        lambda: poisson_arrivals(-1.0, 1.0, 1),
        lambda: bursty_arrivals(1.0, 2.0, 1.1, 1.0, 1.0, 1),
    ],
)
def test_arrival_boundaries_fail_clearly(factory: object) -> None:
    with pytest.raises(ValueError):
        factory()  # type: ignore[operator]


def test_prompt_set_is_deterministic_and_respects_buckets() -> None:
    buckets = (
        PromptBucket("short", 8, 16, 0.5),
        PromptBucket("medium", 17, 32, 0.5),
    )
    tokenizer = WhitespaceTokenCounter()

    first = build_prompt_set(tokenizer, buckets, prompts_per_bucket=2, seed=1729)
    second = build_prompt_set(tokenizer, buckets, prompts_per_bucket=2, seed=1729)

    assert first == second
    assert len(first) == 4
    assert all(prompt.tokenizer_revision == "whitespace-v1" for prompt in first)
    validate_prompt_counts(first, buckets)


def test_prompt_set_rejects_unfillable_bucket(tmp_path: Path) -> None:
    seed_file = tmp_path / "seeds.jsonl"
    seed_file.write_text(
        '{"seed_id":"one","text":"one two three"}\n', encoding="utf-8"
    )
    buckets = (PromptBucket("too-small", 1, 2, 1.0),)

    with pytest.raises(PromptGenerationError, match="cannot fit bucket"):
        build_prompt_set(
            WhitespaceTokenCounter(),
            buckets,
            prompts_per_bucket=1,
            seed=1,
            seeds_path=seed_file,
        )
