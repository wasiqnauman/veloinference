"""API route definitions."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request, status

from gateway.core.batcher import BatcherStoppedError, QueueOverloadedError
from gateway.core.models import HealthResponse, InferenceRequest, InferenceResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def healthcheck(request: Request) -> HealthResponse:
    return HealthResponse(**request.app.state.health)


@router.post("/v1/infer", response_model=InferenceResponse)
async def infer(request: Request, payload: InferenceRequest) -> InferenceResponse:
    service = request.app.state.inference_service
    experiment_id = request.headers.get("X-ADIP-Experiment-ID")
    try:
        return await service.infer(payload, experiment_id=experiment_id)
    except QueueOverloadedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway queue is full",
        ) from exc
    except BatcherStoppedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway is shutting down",
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="Backend request timed out",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Backend inference failed",
        ) from exc
