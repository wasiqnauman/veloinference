"""HTTP clients for direct vLLM and ADIP benchmark targets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import httpx

from bench.schema import PlannedRequest


@dataclass(frozen=True, slots=True)
class ClientResult:
    """Common response shape consumed by the later open-loop runner."""

    output_text: str
    output_tokens: int | None
    batch_id: str | None
    batch_size: int
    queue_ms: float | None
    backend_ms: float | None
    status_code: int


class InferenceClient(Protocol):
    """Interface implemented by every benchmark target client."""

    async def infer(self, request: PlannedRequest) -> ClientResult:
        """Send one request and return normalized client-side timing."""

    async def aclose(self) -> None:
        """Close the underlying HTTP transport."""


class DirectVllmClient:
    """Call the OpenAI-compatible vLLM completions endpoint."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8001",
        timeout_s: float = 120.0,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._headers = (
            {"Authorization": f"Bearer {api_key}"} if api_key is not None else {}
        )
        self._closed = False

    async def infer(self, request: PlannedRequest) -> ClientResult:
        """Send one string prompt to vLLM and normalize its first choice."""

        response = await self._post(
            "/v1/completions",
            {
                "model": request.model,
                "prompt": request.prompt,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
            },
        )
        choices = response.json().get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("vLLM response choices must contain exactly one item")
        choice = choices[0]
        if not isinstance(choice, dict) or not isinstance(choice.get("text"), str):
            raise TypeError("vLLM completion choice text must be a string")
        usage = response.json().get("usage")
        return ClientResult(
            output_text=choice["text"],
            output_tokens=_completion_tokens(usage),
            batch_id=None,
            batch_size=1,
            queue_ms=None,
            backend_ms=None,
            status_code=response.status_code,
        )

    async def _post(self, path: str, payload: dict[str, object]) -> httpx.Response:
        if self._closed:
            raise RuntimeError("DirectVllmClient is closed")
        response = await self._client.post(
            f"{self._base_url}/{path.lstrip('/')}",
            json=payload,
            headers=self._headers,
        )
        response.raise_for_status()
        if not isinstance(response.json(), dict):
            raise TypeError("vLLM response must be a JSON object")
        return response

    async def aclose(self) -> None:
        """Close the HTTP client; repeated calls are safe."""

        if not self._closed:
            self._closed = True
            await self._client.aclose()


class AdipClient:
    """Call ADIP's normalized inference endpoint."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout_s: float = 120.0,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._headers = (
            {"Authorization": f"Bearer {api_key}"} if api_key is not None else {}
        )
        self._closed = False

    async def infer(self, request: PlannedRequest) -> ClientResult:
        """Send one ADIP request and normalize gateway timing fields."""

        if self._closed:
            raise RuntimeError("AdipClient is closed")
        headers = dict(self._headers)
        headers["X-ADIP-Experiment-ID"] = request.experiment_id
        response = await self._client.post(
            f"{self._base_url}/v1/infer",
            json={
                "input_text": request.prompt,
                "model": request.model,
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "deadline_ms": request.deadline_ms,
            },
            headers=headers,
        )
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("ADIP response must be a JSON object")
        return ClientResult(
            output_text=_required_string(body, "output_text"),
            output_tokens=_optional_nonnegative_int(body, "output_tokens"),
            batch_id=_optional_string(body, "batch_id"),
            batch_size=_required_positive_int(body, "batch_size"),
            queue_ms=_optional_nonnegative_float(body, "queue_ms"),
            backend_ms=_optional_nonnegative_float(body, "backend_ms"),
            status_code=response.status_code,
        )

    async def aclose(self) -> None:
        """Close the HTTP client; repeated calls are safe."""

        if not self._closed:
            self._closed = True
            await self._client.aclose()


def _completion_tokens(value: object) -> int | None:
    if not isinstance(value, dict):
        return None
    tokens = value.get("completion_tokens")
    if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
        return tokens
    return None


def _required_string(body: dict[str, object], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str):
        raise TypeError(f"ADIP response {key} must be a string")
    return value


def _optional_string(body: dict[str, object], key: str) -> str | None:
    value = body.get(key)
    if value is not None and not isinstance(value, str):
        raise TypeError(f"ADIP response {key} must be a string or null")
    return value


def _required_positive_int(body: dict[str, object], key: str) -> int:
    value = body.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypeError(f"ADIP response {key} must be a positive integer")
    return value


def _optional_nonnegative_int(body: dict[str, object], key: str) -> int | None:
    value = body.get(key)
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise TypeError(f"ADIP response {key} must be a non-negative integer or null")
    return value


def _optional_nonnegative_float(body: dict[str, object], key: str) -> float | None:
    value = body.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise TypeError(f"ADIP response {key} must be a non-negative number or null")
    return float(value)
