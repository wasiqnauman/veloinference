"""Application entrypoint."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import uvicorn
from fastapi import FastAPI

from gateway.api.routes import router
from gateway.backends.factory import build_backend
from gateway.config import settings
from gateway.core.batcher import DynamicBatcher
from gateway.core.service import InferenceService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    backend = build_backend(settings)
    batcher = DynamicBatcher(
        backend=backend,
        max_batch_size=settings.batch_max_size,
        max_wait_ms=settings.batch_max_wait_ms,
        queue_max_size=settings.queue_max_size,
    )
    await batcher.start()
    app.state.inference_service = InferenceService(backend=backend, batcher=batcher)

    try:
        yield
    finally:
        await batcher.stop()
        aclose = getattr(backend, "aclose", None)
        if aclose is not None:
            await aclose()


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
