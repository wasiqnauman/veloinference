"""Shared core models."""

from dataclasses import dataclass
from time import monotonic
from typing import Self
from uuid import uuid4

from pydantic import BaseModel, Field


class InferenceRequest(BaseModel):
    input_text: str = Field(min_length=1)
    model: str = "mock"
    deadline_ms: int | None = Field(default=None, ge=1)


class InferenceResponse(BaseModel):
    request_id: str
    model: str
    output_text: str
    batch_size: int


class HealthResponse(BaseModel):
    status: str


class BatchMetadata(BaseModel):
    request_id: str
    model: str
    enqueued_at: float
    deadline_ms: int | None

    @classmethod
    def create(cls, request: InferenceRequest) -> Self:
        return cls(
            request_id=str(uuid4()),
            model=request.model,
            enqueued_at=monotonic(),
            deadline_ms=request.deadline_ms,
        )


@dataclass(slots=True)
class PendingRequest:
    metadata: BatchMetadata
    payload: InferenceRequest
    future: object
