"""MockTransport tests for the vLLM backend adapter."""

import json
from collections.abc import Callable

import httpx
import pytest

from gateway.backends.vllm import VllmBackend
from gateway.clients.backend_http import BackendHttpClient
from gateway.core.models import BatchMetadata, InferenceRequest, PendingRequest


def pending(request: InferenceRequest) -> PendingRequest:
    return PendingRequest(
        metadata=BatchMetadata.create(request),
        payload=request,
        future=None,
    )


def make_backend(
    handler: Callable[[httpx.Request], httpx.Response],
) -> VllmBackend:
    client = BackendHttpClient(
        base_url="http://vllm",
        timeout_s=10.0,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    return VllmBackend(client)


@pytest.mark.asyncio
async def test_infer_one_builds_completion_payload_and_reads_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/completions"
        assert json.loads(request.content) == {
            "model": "qwen",
            "prompt": "hello",
            "max_tokens": 32,
            "temperature": 0.2,
        }
        return httpx.Response(
            200,
            json={
                "choices": [{"index": 0, "text": "world"}],
                "usage": {"completion_tokens": 7},
            },
        )

    backend = make_backend(handler)
    try:
        output = await backend.infer_one(
            pending(
                InferenceRequest(
                    input_text="hello",
                    model="qwen",
                    max_tokens=32,
                    temperature=0.2,
                )
            )
        )
    finally:
        await backend.aclose()

    assert output.output_text == "world"
    assert output.output_tokens == 7


@pytest.mark.asyncio
async def test_infer_batch_orders_indexed_choices_and_reads_per_choice_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["prompt"] == ["one", "two"]
        assert body["model"] == "qwen"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 1,
                        "text": "TWO",
                        "usage": {"completion_tokens": 4},
                    },
                    {
                        "index": 0,
                        "text": "ONE",
                        "usage": {"completion_tokens": 3},
                    },
                ],
                "usage": {"completion_tokens": 7},
            },
        )

    backend = make_backend(handler)
    requests = [
        pending(InferenceRequest(input_text="one", model="qwen")),
        pending(InferenceRequest(input_text="two", model="qwen")),
    ]
    try:
        outputs = await backend.infer_batch(requests)
    finally:
        await backend.aclose()

    assert [output.output_text for output in outputs] == ["ONE", "TWO"]
    assert [output.output_tokens for output in outputs] == [3, 4]


@pytest.mark.asyncio
async def test_infer_batch_rejects_incompatible_requests_before_http() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP must not be called for an incompatible batch")

    backend = make_backend(handler)
    requests = [
        pending(InferenceRequest(input_text="one", model="qwen")),
        pending(InferenceRequest(input_text="two", model="other")),
    ]
    try:
        with pytest.raises(ValueError, match="same BatchKey"):
            await backend.infer_batch(requests)
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_infer_batch_rejects_choice_count_mismatch() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"text": "only-one"}]})

    backend = make_backend(handler)
    requests = [
        pending(InferenceRequest(input_text="one", model="qwen")),
        pending(InferenceRequest(input_text="two", model="qwen")),
    ]
    try:
        with pytest.raises(ValueError, match="choice count"):
            await backend.infer_batch(requests)
    finally:
        await backend.aclose()


@pytest.mark.asyncio
async def test_backend_close_is_safe_to_repeat() -> None:
    backend = make_backend(lambda _: httpx.Response(200, json={"choices": []}))
    await backend.aclose()
    await backend.aclose()
