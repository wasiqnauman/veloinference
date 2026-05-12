"""vLLM backend adapter."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from gateway.backends.base import InferenceBackend
from gateway.core.models import PendingRequest


class VllmBackend(InferenceBackend):
    def __init__(
        self,
        base_url: str,
        default_model: str,
        api_key: str | None,
        timeout_s: float,
        max_tokens: int,
        temperature: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._default_model = default_model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            headers=headers,
        )

    async def infer_one(self, request: PendingRequest) -> str:
        body = await self._submit_completion(
            prompts=request.payload.input_text,
            model=self._resolve_model(request),
        )
        return self._extract_single_output(body)

    async def infer_batch(self, requests: Sequence[PendingRequest]) -> list[str]:
        if not requests:
            return []

        model = self._resolve_model(requests[0])
        if any(self._resolve_model(request) != model for request in requests[1:]):
            raise RuntimeError("vLLM batches currently require all requests to target the same model")

        body = await self._submit_completion(
            prompts=[request.payload.input_text for request in requests],
            model=model,
        )
        return self._extract_batch_outputs(body, expected_size=len(requests))

    def _resolve_model(self, request: PendingRequest) -> str:
        model = request.payload.model.strip()
        if not model or model == "mock":
            return self._default_model
        return model

    async def _submit_completion(self, prompts: str | list[str], model: str) -> dict[str, Any]:
        payload = {
            "model": model,
            "prompt": prompts,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        response = await self._client.post("/v1/completions", json=payload)
        response.raise_for_status()
        return response.json()

    def _extract_single_output(self, body: dict[str, Any]) -> str:
        choices = body.get("choices", [])
        if not choices:
            raise RuntimeError("vLLM returned no completion choices")
        return str(choices[0].get("text", ""))

    def _extract_batch_outputs(self, body: dict[str, Any], expected_size: int) -> list[str]:
        choices = body.get("choices", [])
        if len(choices) != expected_size:
            raise RuntimeError(
                "vLLM returned an unexpected number of completion choices: "
                f"expected {expected_size}, got {len(choices)}"
            )

        return [str(choice.get("text", "")) for choice in choices]

    async def aclose(self) -> None:
        await self._client.aclose()
