"""Deterministic, project-authored prompt preparation for benchmark runs."""

from __future__ import annotations

import json
import random
from collections.abc import Iterable, Protocol
from pathlib import Path
from typing import Any

from bench.schema import PreparedPrompt, PromptBucket


DEFAULT_SEEDS_PATH = Path(__file__).with_name("data") / "prompt_seeds.jsonl"


class PromptGenerationError(ValueError):
    """Raised when project-authored seeds cannot satisfy a token bucket."""


class TokenCounter(Protocol):
    """Minimal tokenizer adapter required by prompt generation."""

    @property
    def revision(self) -> str:
        """Return the exact tokenizer/model revision used for counting."""

    def count(self, text: str) -> int:
        """Return the model tokenizer's input-token count for ``text``."""


class WhitespaceTokenCounter:
    """Explicitly non-final fallback counter for local parser and smoke tests."""

    revision = "whitespace-v1"

    def count(self, text: str) -> int:
        return len(text.split())


def load_prompt_seeds(path: Path = DEFAULT_SEEDS_PATH) -> tuple[tuple[str, str], ...]:
    """Load ``(seed_id, text)`` pairs from project-authored JSONL."""

    if not path.is_file():
        raise PromptGenerationError(f"prompt seed file does not exist: {path}")

    seeds: list[tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value: Any = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PromptGenerationError(
                f"invalid JSON in prompt seed file at line {line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise PromptGenerationError(f"prompt seed line {line_number} must be an object")
        seed_id = value.get("seed_id")
        text = value.get("text")
        if not isinstance(seed_id, str) or not seed_id.strip():
            raise PromptGenerationError(
                f"prompt seed line {line_number} requires a non-empty seed_id"
            )
        if not isinstance(text, str) or not text.strip():
            raise PromptGenerationError(
                f"prompt seed line {line_number} requires non-empty text"
            )
        seeds.append((seed_id.strip(), " ".join(text.split())))

    if not seeds:
        raise PromptGenerationError(f"prompt seed file is empty: {path}")
    return tuple(seeds)


def build_prompt_set(
    tokenizer: TokenCounter,
    buckets: tuple[PromptBucket, ...],
    prompts_per_bucket: int,
    seed: int,
    *,
    seeds_path: Path = DEFAULT_SEEDS_PATH,
) -> tuple[PreparedPrompt, ...]:
    """Return deterministic prompts whose token counts satisfy every bucket."""

    if prompts_per_bucket <= 0:
        raise ValueError("prompts_per_bucket must be greater than 0")
    if not buckets:
        raise ValueError("buckets must not be empty")

    seeds = list(load_prompt_seeds(seeds_path))
    generator = random.Random(seed)
    generator.shuffle(seeds)
    prompts: list[PreparedPrompt] = []

    for bucket in buckets:
        for prompt_index in range(prompts_per_bucket):
            seed_id, text, token_count = _fit_seed_to_bucket(
                tokenizer,
                bucket,
                seeds[(len(prompts) + prompt_index) % len(seeds)],
            )
            prompts.append(
                PreparedPrompt(
                    text=text,
                    input_tokens=token_count,
                    seed_id=seed_id,
                    tokenizer_revision=tokenizer.revision,
                    bucket_name=bucket.name,
                )
            )
    return tuple(prompts)


def _fit_seed_to_bucket(
    tokenizer: TokenCounter,
    bucket: PromptBucket,
    seed: tuple[str, str],
) -> tuple[str, str, int]:
    seed_id, seed_text = seed
    candidate = seed_text
    for _ in range(bucket.maximum_tokens):
        token_count = tokenizer.count(candidate)
        if bucket.minimum_tokens <= token_count <= bucket.maximum_tokens:
            return seed_id, candidate, token_count
        if token_count > bucket.maximum_tokens:
            break
        candidate = f"{candidate} {seed_text}"
    raise PromptGenerationError(
        f"seed {seed_id!r} cannot fit bucket {bucket.name!r} with range "
        f"{bucket.minimum_tokens}-{bucket.maximum_tokens} tokens"
    )


def validate_prompt_counts(
    prompts: Iterable[PreparedPrompt], buckets: tuple[PromptBucket, ...]
) -> None:
    """Raise if any prepared prompt falls outside its declared bucket."""

    ranges = {bucket.name: bucket for bucket in buckets}
    for prompt in prompts:
        bucket = ranges.get(prompt.bucket_name)
        if bucket is None:
            raise PromptGenerationError(
                f"prepared prompt references unknown bucket {prompt.bucket_name!r}"
            )
        if not bucket.minimum_tokens <= prompt.input_tokens <= bucket.maximum_tokens:
            raise PromptGenerationError(
                f"prompt {prompt.seed_id!r} has {prompt.input_tokens} tokens, "
                f"outside bucket {bucket.name!r}"
            )
