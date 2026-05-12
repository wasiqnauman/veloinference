"""API route definitions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from gateway.core.batcher import QueueOverloadedError
from gateway.core.models import HealthResponse, InferenceRequest, InferenceResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def healthcheck() -> HealthResponse:
    return HealthResponse(status="ok")


@router.post("/v1/infer", response_model=InferenceResponse)
async def infer(request: Request, payload: InferenceRequest) -> InferenceResponse:
    service = request.app.state.inference_service
    try:
        return await service.infer(payload)
    except QueueOverloadedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway queue is full",
        ) from exc


@router.post("/v1/infer/direct", response_model=InferenceResponse)
async def infer_direct(request: Request, payload: InferenceRequest) -> InferenceResponse:
    service = request.app.state.inference_service
    return await service.infer_direct(payload)
