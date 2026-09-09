"""Shared core models."""

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, Field

from gateway.core.clock import Clock


class InferenceRequest(BaseModel):
    input_text: str = Field(min_length=1)
    model: str = Field(default="mock", min_length=1)
    max_tokens: int = Field(default=64, ge=1, le=256)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    deadline_ms: int | None = Field(default=None, ge=1)


class InferenceResponse(BaseModel):
    request_id: str
    model: str
    output_text: str
    batch_size: int
    output_tokens: int | None = None
    batch_id: str | None = None
    queue_ms: float = 0.0
    backend_ms: float = 0.0
    total_ms: float = 0.0
    deadline_met: bool | None = None


class HealthResponse(BaseModel):
    status: str


@dataclass(frozen=True, slots=True)
class BatchKey:
    """Request attributes that must match for backend batching."""

    model: str
    max_tokens: int
    temperature: float

    @classmethod
    def from_request(cls, request: InferenceRequest) -> Self:
        """Create a compatibility key from a validated request."""
        return cls(
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )


class BatchMetadata(BaseModel):
    request_id: str
    model: str
    enqueued_at: float
    deadline_ms: int | None
    max_tokens: int = Field(default=64, ge=1, le=256)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)

    @classmethod
    def create(cls, request: InferenceRequest, clock: Clock | None = None) -> Self:
        return cls(
            request_id=str(uuid4()),
            model=request.model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            enqueued_at=clock.monotonic() if clock is not None else monotonic(),
            deadline_ms=request.deadline_ms,
        )

    @property
    def batch_key(self) -> BatchKey:
        """Return the compatibility key for this request."""
        return BatchKey(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )


@dataclass(slots=True)
class PendingRequest:
    metadata: BatchMetadata
    payload: InferenceRequest
    future: asyncio.Future[InferenceResponse] | None
