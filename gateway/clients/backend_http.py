"""Shared asynchronous HTTP transport for backend integrations."""

from __future__ import annotations

from collections.abc import Mapping

import httpx


class BackendHttpClient:
    """Send JSON requests through one reusable asynchronous HTTP client.

    The wrapper owns the supplied client and closes it at most once. A client
    can be injected by tests so all transport behavior remains deterministic
    without requiring a live backend.
    """

    def __init__(
        self,
        base_url: str,
        timeout_s: float,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self._headers: Mapping[str, str] = (
            {"Authorization": f"Bearer {api_key}"} if api_key else {}
        )
        self._closed = False

    async def post_json(
        self,
        path: str,
        payload: dict[str, object],
    ) -> dict[str, object]:
        """POST JSON and return a JSON object from a successful response.

        HTTP errors are raised by ``httpx``. Responses containing valid JSON
        arrays, strings, numbers, booleans, or null are rejected because
        backend adapters require an object-shaped response.
        """
        if self._closed:
            raise RuntimeError("BackendHttpClient is closed")

        url = f"{self._base_url}/{path.lstrip('/')}"
        response = await self._client.post(
            url,
            json=payload,
            headers=self._headers,
        )
        response.raise_for_status()

        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("Backend response must be a JSON object")
        return data

    async def aclose(self) -> None:
        """Close the underlying client; repeated calls are harmless."""
        if self._closed:
            return
        self._closed = True
        await self._client.aclose()
