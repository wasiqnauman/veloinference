"""vLLM OpenAI-compatible completions backend adapter."""

from __future__ import annotations

from collections.abc import Sequence

from gateway.backends.base import InferenceBackend
from gateway.clients.backend_http import BackendHttpClient
from gateway.core.models import BackendOutput, PendingRequest


class VllmBackend(InferenceBackend):
    """Translate compatible ADIP requests to vLLM completion requests."""

    def __init__(
        self,
        client: BackendHttpClient,
        endpoint: str = "/v1/completions",
    ) -> None:
        self._client = client
        self._endpoint = endpoint

    async def infer_one(self, request: PendingRequest) -> BackendOutput:
        """Send one prompt as a string and normalize its completion."""
        payload = self._build_payload(request, request.payload.input_text)
        response = await self._client.post_json(self._endpoint, payload)
        return self._parse_outputs(response, expected_count=1)[0]

    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[BackendOutput]:
        """Send compatible prompts as one list and restore input order."""
        request_list = list(requests)
        if not request_list:
            return []

        self._ensure_compatible(request_list)
        payload = self._build_payload(
            request_list[0],
            [request.payload.input_text for request in request_list],
        )
        response = await self._client.post_json(self._endpoint, payload)
        return self._parse_outputs(response, expected_count=len(request_list))

    async def aclose(self) -> None:
        """Close the shared HTTP transport."""
        await self._client.aclose()

    @staticmethod
    def _ensure_compatible(requests: Sequence[PendingRequest]) -> None:
        first_key = requests[0].metadata.batch_key
        if any(request.metadata.batch_key != first_key for request in requests[1:]):
            raise ValueError("All requests in a vLLM batch must have the same BatchKey")

    @staticmethod
    def _build_payload(
        request: PendingRequest,
        prompt: str | list[str],
    ) -> dict[str, object]:
        return {
            "model": request.payload.model,
            "prompt": prompt,
            "max_tokens": request.payload.max_tokens,
            "temperature": request.payload.temperature,
        }

    @classmethod
    def _parse_outputs(
        cls,
        response: dict[str, object],
        expected_count: int,
    ) -> list[BackendOutput]:
        choices = response.get("choices")
        if not isinstance(choices, list):
            raise TypeError("vLLM response choices must be a list")
        if len(choices) != expected_count:
            raise ValueError(
                "vLLM response choice count does not match request count"
            )

        indexed_choices = cls._order_choices(choices, expected_count)
        top_level_tokens = cls._completion_tokens(response.get("usage"))
        outputs: list[BackendOutput] = []
        for position, choice in enumerate(indexed_choices):
            if not isinstance(choice, dict):
                raise TypeError("vLLM completion choice must be an object")
            text = choice.get("text")
            if not isinstance(text, str):
                raise TypeError("vLLM completion choice text must be a string")
            output_tokens = cls._completion_tokens(choice.get("usage"))
            if expected_count == 1 and output_tokens is None:
                output_tokens = top_level_tokens
            outputs.append(
                BackendOutput(
                    output_text=text,
                    output_tokens=output_tokens,
                )
            )
            if position == expected_count - 1:
                break
        return outputs

    @staticmethod
    def _order_choices(
        choices: list[object],
        expected_count: int,
    ) -> list[object]:
        indices: list[int | None] = []
        for choice in choices:
            if not isinstance(choice, dict):
                indices.append(None)
                continue
            index = choice.get("index")
            if index is not None and (
                not isinstance(index, int) or isinstance(index, bool)
            ):
                raise ValueError("vLLM choice index must be an integer")
            indices.append(index)

        if all(index is None for index in indices):
            return choices
        if any(index is None for index in indices):
            raise ValueError("vLLM choices must all include index or all omit it")

        ordered: list[object | None] = [None] * expected_count
        for choice, index in zip(choices, indices, strict=True):
            assert index is not None
            if index < 0 or index >= expected_count or ordered[index] is not None:
                raise ValueError("vLLM choice indices must be unique and in range")
            ordered[index] = choice
        if any(choice is None for choice in ordered):
            raise ValueError("vLLM choice indices must cover every request")
        return [choice for choice in ordered if choice is not None]

    @staticmethod
    def _completion_tokens(value: object) -> int | None:
        if not isinstance(value, dict):
            return None
        tokens = value.get("completion_tokens")
        if isinstance(tokens, int) and not isinstance(tokens, bool) and tokens >= 0:
            return tokens
        return None
