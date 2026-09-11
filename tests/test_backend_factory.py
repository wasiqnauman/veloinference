"""Backend factory tests."""

import pytest

from gateway.backends.factory import build_backend
from gateway.backends.mock import MockBackend
from gateway.backends.vllm import VllmBackend
from gateway.config import Settings


def test_build_backend_selects_mock() -> None:
    backend = build_backend(Settings(backend_kind="mock"))

    assert isinstance(backend, MockBackend)


@pytest.mark.asyncio
async def test_build_backend_selects_vllm_and_closes_transport() -> None:
    backend = build_backend(
        Settings(
            backend_kind="vllm",
            vllm_base_url="http://127.0.0.1:8001",
        )
    )

    assert isinstance(backend, VllmBackend)
    await backend.aclose()
