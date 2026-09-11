"""MockTransport tests for benchmark target clients."""

from __future__ import annotations

import json

import httpx
import pytest

from bench.client import AdipClient, DirectVllmClient
from bench.schema import PlannedRequest


def planned_request() -> PlannedRequest:
    return PlannedRequest(
        schema_version=1,
        experiment_id="bench-test",
        run_id="run-1",
        request_index=0,
        policy="fixed",
        model="qwen",
        workload="short",
        seed=1729,
        arrival_offset_s=0.0,
        prompt="hello",
        input_tokens=1,
        max_tokens=32,
        temperature=0.2,
        deadline_ms=750,
    )


@pytest.mark.asyncio
async def test_direct_vllm_client_uses_shared_request_fields() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/completions"
        assert "x-adip-experiment-id" not in request.headers
        assert json.loads(request.content) == {
            "model": "qwen",
            "prompt": "hello",
            "max_tokens": 32,
            "temperature": 0.2,
        }
        return httpx.Response(
            200,
            json={"choices": [{"text": "world"}], "usage": {"completion_tokens": 7}},
        )

    client = DirectVllmClient(
        base_url="http://vllm",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        result = await client.infer(planned_request())
    finally:
        await client.aclose()

    assert result.output_text == "world"
    assert result.output_tokens == 7
    assert result.batch_size == 1
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_adip_client_normalizes_gateway_fields_and_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/infer"
        assert request.headers["x-adip-experiment-id"] == "bench-test"
        assert json.loads(request.content) == {
            "input_text": "hello",
            "model": "qwen",
            "max_tokens": 32,
            "temperature": 0.2,
            "deadline_ms": 750,
        }
        return httpx.Response(
            200,
            json={
                "output_text": "world",
                "output_tokens": 7,
                "batch_id": "batch-1",
                "batch_size": 3,
                "queue_ms": 1.25,
                "backend_ms": 8,
            },
        )

    client = AdipClient(
        base_url="http://adip",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    try:
        result = await client.infer(planned_request())
    finally:
        await client.aclose()

    assert result.output_text == "world"
    assert result.output_tokens == 7
    assert result.batch_id == "batch-1"
    assert result.batch_size == 3
    assert result.queue_ms == 1.25
    assert result.backend_ms == 8.0


@pytest.mark.asyncio
async def test_clients_reject_malformed_normalized_response() -> None:
    direct = DirectVllmClient(
        base_url="http://vllm",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"choices": []})
            )
        ),
    )
    adip = AdipClient(
        base_url="http://adip",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    200, json={"output_text": "ok", "batch_size": 0}
                )
            )
        ),
    )
    try:
        with pytest.raises(ValueError, match="exactly one"):
            await direct.infer(planned_request())
        with pytest.raises(TypeError, match="positive integer"):
            await adip.infer(planned_request())
    finally:
        await direct.aclose()
        await adip.aclose()


@pytest.mark.asyncio
async def test_client_close_is_idempotent_and_blocks_future_requests() -> None:
    client = DirectVllmClient(
        base_url="http://vllm",
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={}))
        ),
    )
    await client.aclose()
    await client.aclose()

    with pytest.raises(RuntimeError, match="closed"):
        await client.infer(planned_request())
