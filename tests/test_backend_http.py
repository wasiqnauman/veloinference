"""Tests for the shared backend HTTP transport."""

import json

import httpx
import pytest

from gateway.clients.backend_http import BackendHttpClient


@pytest.mark.asyncio
async def test_post_json_sends_payload_and_optional_bearer_header() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    backend = BackendHttpClient(
        base_url="http://backend/",
        timeout_s=2.0,
        api_key="test-secret",
        client=client,
    )

    try:
        result = await backend.post_json(
            "/v1/completions",
            {"model": "mock", "prompt": "hello"},
        )
    finally:
        await backend.aclose()

    assert result == {"ok": True}
    assert len(requests) == 1
    assert str(requests[0].url) == "http://backend/v1/completions"
    assert requests[0].headers["authorization"] == "Bearer test-secret"
    assert json.loads(requests[0].content) == {"model": "mock", "prompt": "hello"}


@pytest.mark.asyncio
async def test_post_json_omits_authorization_when_key_is_not_configured() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"ok": True})

    backend = BackendHttpClient(
        base_url="http://backend",
        timeout_s=2.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        assert await backend.post_json("health", {}) == {"ok": True}
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_post_json_rejects_non_success_status() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    backend = BackendHttpClient(
        base_url="http://backend",
        timeout_s=2.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        with pytest.raises(httpx.HTTPStatusError):
            await backend.post_json("health", {})
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_post_json_rejects_non_object_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"ok": True}])

    backend = BackendHttpClient(
        base_url="http://backend",
        timeout_s=2.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        with pytest.raises(TypeError, match="JSON object"):
            await backend.post_json("health", {})
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_post_json_rejects_malformed_json() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    backend = BackendHttpClient(
        base_url="http://backend",
        timeout_s=2.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    try:
        with pytest.raises(ValueError):
            await backend.post_json("health", {})
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_aclose_is_idempotent_and_blocks_future_requests() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json={}))
    backend = BackendHttpClient(
        base_url="http://backend",
        timeout_s=2.0,
        client=httpx.AsyncClient(transport=transport),
    )

    await backend.aclose()
    await backend.aclose()

    with pytest.raises(RuntimeError, match="closed"):
        await backend.post_json("health", {})
