"""vLLM backend tests."""

import asyncio
import json

import httpx
import pytest

from gateway.backends.vllm import VllmBackend
from gateway.core.models import BatchMetadata, InferenceRequest, PendingRequest


def build_pending_request(text: str, model: str = "mock") -> PendingRequest:
    payload = InferenceRequest(input_text=text, model=model)
    return PendingRequest(
        metadata=BatchMetadata.create(payload),
        payload=payload,
        future=asyncio.get_running_loop().create_future(),
    )


@pytest.mark.asyncio
async def test_vllm_backend_uses_default_model_for_placeholder_requests() -> None:
    captured_payloads: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payloads.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"choices": [{"text": "hello"}]})

    client = httpx.AsyncClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )
    backend = VllmBackend(
        base_url="http://testserver",
        default_model="meta-llama/Llama-3.2-1B-Instruct",
        api_key=None,
        timeout_s=5.0,
        max_tokens=32,
        temperature=0.0,
        client=client,
    )

    try:
        output = await backend.infer_one(build_pending_request("hello", model="mock"))
    finally:
        await backend.aclose()

    assert output == "hello"
    assert captured_payloads[0]["model"] == "meta-llama/Llama-3.2-1B-Instruct"


@pytest.mark.asyncio
async def test_vllm_backend_preserves_batched_output_order() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        prompts = payload["prompt"]
        return httpx.Response(
            200,
            json={"choices": [{"text": f"out:{prompt}"} for prompt in prompts]},
        )

    client = httpx.AsyncClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )
    backend = VllmBackend(
        base_url="http://testserver",
        default_model="meta-llama/Llama-3.2-1B-Instruct",
        api_key=None,
        timeout_s=5.0,
        max_tokens=32,
        temperature=0.0,
        client=client,
    )

    try:
        outputs = await backend.infer_batch(
            [build_pending_request("one"), build_pending_request("two")]
        )
    finally:
        await backend.aclose()

    assert outputs == ["out:one", "out:two"]


@pytest.mark.asyncio
async def test_vllm_backend_rejects_mixed_model_batches() -> None:
    client = httpx.AsyncClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})),
    )
    backend = VllmBackend(
        base_url="http://testserver",
        default_model="meta-llama/Llama-3.2-1B-Instruct",
        api_key=None,
        timeout_s=5.0,
        max_tokens=32,
        temperature=0.0,
        client=client,
    )

    with pytest.raises(RuntimeError, match="same model"):
        try:
            await backend.infer_batch(
                [
                    build_pending_request("one", model="model-a"),
                    build_pending_request("two", model="model-b"),
                ]
            )
        finally:
            await backend.aclose()
