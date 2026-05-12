"""Backend factory tests."""

import pytest

from gateway.backends.factory import build_backend
from gateway.backends.mock import MockBackend
from gateway.backends.vllm import VllmBackend
from gateway.config import Settings


def test_build_backend_returns_mock_backend() -> None:
    backend = build_backend(Settings(backend_kind="mock"))

    assert isinstance(backend, MockBackend)


@pytest.mark.asyncio
async def test_build_backend_returns_vllm_backend() -> None:
    backend = build_backend(
        Settings(
            backend_kind="vllm",
            vllm_base_url="http://127.0.0.1:8001",
            vllm_model="meta-llama/Llama-3.2-1B-Instruct",
        )
    )

    try:
        assert isinstance(backend, VllmBackend)
    finally:
        await backend.aclose()
