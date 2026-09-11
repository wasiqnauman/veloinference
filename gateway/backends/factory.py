"""Construct the configured inference backend."""

from gateway.backends.base import InferenceBackend
from gateway.backends.mock import MockBackend
from gateway.backends.vllm import VllmBackend
from gateway.clients.backend_http import BackendHttpClient
from gateway.config import Settings


def build_backend(settings: Settings) -> InferenceBackend:
    """Construct the mock or vLLM backend selected by validated settings."""
    if settings.backend_kind == "mock":
        return MockBackend(
            base_latency_ms=settings.mock_backend_base_latency_ms,
            per_item_latency_ms=settings.mock_backend_per_item_latency_ms,
        )

    if settings.backend_kind == "vllm":
        client = BackendHttpClient(
            base_url=settings.vllm_base_url,
            timeout_s=settings.vllm_timeout_s,
            api_key=settings.vllm_api_key,
        )
        return VllmBackend(client)

    raise ValueError(f"Unsupported backend kind: {settings.backend_kind}")
