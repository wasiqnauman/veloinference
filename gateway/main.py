"""Application entrypoint."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from gateway.api.routes import router
from gateway.backends.mock import MockBackend
from gateway.config import settings
from gateway.core.batcher import DynamicBatcher


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    backend = MockBackend(
        base_latency_ms=settings.mock_backend_base_latency_ms,
        per_item_latency_ms=settings.mock_backend_per_item_latency_ms,
    )
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=settings.batch_max_size,
        max_wait_ms=settings.batch_max_wait_ms,
        queue_max_size=settings.queue_max_size,
    )
    await batcher.start()
    app.state.batcher = batcher

    try:
        yield
    finally:
        await batcher.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
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
