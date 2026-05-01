"""Internal type definitions."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from gateway.core.models import PendingRequest


class BatchBackend(Protocol):
    async def infer_batch(self, requests: Sequence[PendingRequest]) -> list[str]:
        """Run inference for a batch and return outputs in request order."""
