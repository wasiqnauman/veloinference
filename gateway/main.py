"""Application composition and lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from gateway.api.routes import router
from gateway.backends.base import InferenceBackend
from gateway.backends.factory import build_backend
from gateway.config import Settings, settings
from gateway.core.batcher import DynamicBatcher
from gateway.core.clock import SystemClock
from gateway.core.policies.base import BatchPolicy
from gateway.core.policies.fixed import FixedWindowPolicy
from gateway.core.service import InferenceService
from gateway.observability.logging import JsonEventLogger, NullEventLogger
from gateway.observability.metrics import MetricsRegistry


def _build_policy(configured: Settings) -> BatchPolicy:
    """Build the policy supported by the current implementation milestone."""
    if configured.batch_policy == "fixed":
        return FixedWindowPolicy()
    raise ValueError(
        "Adaptive policy is reserved for CORE-005; use batch_policy=fixed"
    )


def _build_lifespan(configured: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, configured.log_level.upper(), logging.INFO)
        )
        backend: InferenceBackend = build_backend(configured)
        policy = _build_policy(configured)
        clock = SystemClock()
        event_logger = (
            JsonEventLogger()
            if configured.research_telemetry
            else NullEventLogger()
        )
        metrics = MetricsRegistry(configured.adaptive_ewma_alpha)
        batcher = DynamicBatcher(
            backend=backend,
            max_batch_size=configured.batch_max_size,
            max_wait_ms=configured.batch_max_wait_ms,
            queue_max_size=configured.queue_max_size,
            policy=policy,
            clock=clock,
            event_logger=event_logger,
            metrics=metrics,
        )

        try:
            if configured.gateway_mode == "batched":
                await batcher.start()
            app.state.batcher = batcher
            app.state.inference_service = InferenceService(
                backend=backend,
                batcher=batcher,
                mode=configured.gateway_mode,
                clock=clock,
                event_logger=event_logger,
                metrics=metrics,
            )
            app.state.metrics = metrics
            app.state.health = {
                "status": "ok",
                "backend": configured.backend_kind,
                "mode": configured.gateway_mode,
                "policy": configured.batch_policy,
            }
            yield
        finally:
            try:
                await batcher.stop()
            finally:
                await backend.aclose()

    return lifespan


def create_app(configured: Settings | None = None) -> FastAPI:
    """Create an app with validated settings and an isolated lifespan."""
    app_settings = configured or settings
    app = FastAPI(
        title=app_settings.app_name,
        lifespan=_build_lifespan(app_settings),
    )
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    uvicorn.run(
        "gateway.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
