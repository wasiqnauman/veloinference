"""Backend construction helpers."""

from __future__ import annotations

from gateway.backends.base import InferenceBackend
from gateway.backends.mock import MockBackend
from gateway.backends.vllm import VllmBackend
from gateway.config import Settings


def build_backend(settings: Settings) -> InferenceBackend:
    if settings.backend_kind == "mock":
        return MockBackend(
            base_latency_ms=settings.mock_backend_base_latency_ms,
            per_item_latency_ms=settings.mock_backend_per_item_latency_ms,
        )

    if settings.backend_kind == "vllm":
        return VllmBackend(
            base_url=settings.vllm_base_url,
            default_model=settings.vllm_model,
            api_key=settings.vllm_api_key,
            timeout_s=settings.vllm_timeout_s,
            max_tokens=settings.vllm_max_tokens,
            temperature=settings.vllm_temperature,
        )

    raise ValueError(f"Unsupported backend: {settings.backend_kind}")
