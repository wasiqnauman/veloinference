"""Backend interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from gateway.core.models import BackendOutput, PendingRequest


class InferenceBackend(ABC):
    @abstractmethod
    async def infer_batch(
        self,
        requests: Sequence[PendingRequest],
    ) -> list[BackendOutput]:
        """Run inference for a batch and return outputs in request order."""

    async def infer_one(self, request: PendingRequest) -> BackendOutput:
        """Run one request through the batch interface."""
        outputs = await self.infer_batch([request])
        if len(outputs) != 1:
            raise RuntimeError("Backend returned an unexpected number of responses")
        return outputs[0]

    async def aclose(self) -> None:
        """Release backend resources when the application stops."""
        return
