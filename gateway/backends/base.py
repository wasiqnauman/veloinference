"""Backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from gateway.core.models import PendingRequest


class InferenceBackend(ABC):
    @abstractmethod
    async def infer_batch(self, requests: Sequence[PendingRequest]) -> list[str]:
        """Run inference for a batch and return outputs in request order."""
