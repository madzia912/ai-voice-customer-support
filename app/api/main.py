"""FastAPI application entry point.

Run with::

    uvicorn app.api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from ..config import get_settings
from ..logging_config import configure_logging
from ..messaging import get_rabbitmq_client
from .routes import generate, jobs

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    # Ensure data dirs exist at boot so the static mount + job store work.
    Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.jobs_dir).mkdir(parents=True, exist_ok=True)

    # Pre-open the RabbitMQ connection so the first request is fast and
    # connection problems surface at startup rather than at request time.
    client = get_rabbitmq_client()
    await client.connect()
    logger.info("API ready", extra={"llm_provider": settings.llm_provider})

    try:
        yield
    finally:
        await client.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Voice Orchestration API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(generate.router)
    app.include_router(jobs.router)

    # Serve generated audio files directly from the shared volume.
    Path(settings.audio_dir).mkdir(parents=True, exist_ok=True)
    app.mount("/audio", StaticFiles(directory=settings.audio_dir), name="audio")

    @app.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
