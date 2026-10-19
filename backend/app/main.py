"""create_app: routes, CORS, error handlers, and the DB pool.

Owner: A
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, extract, health, records
from app.api.errors import add_problem_handler
from app.settings import Settings, get_settings
from app.storage.db import open_pool

logger = logging.getLogger(__name__)


def _lifespan(settings: Settings):
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Without DATABASE_URL the app still starts; login and records answer 503.
        # With it, a database that is unreachable or on another schema stops the start.
        url = settings.database_url.get_secret_value()
        app.state.pool = await open_pool(url) if url else None
        if app.state.pool is None:
            logger.warning("DATABASE_URL is not set: login and records answer 503")
        try:
            yield
        finally:
            if app.state.pool is not None:
                await app.state.pool.close()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    if settings.extraction_provider == "fake":
        logger.warning("EXTRACTION_PROVIDER=fake: every answer is a test fixture, not a reading")
    elif settings.extraction_cache:
        logger.warning(
            "EXTRACTION_CACHE=true: pages already read come from backend/.cache "
            "(dev only, sample files only)"
        )
    app = FastAPI(title="virus-lab", lifespan=_lifespan(settings))
    app.state.pool = None  # until the lifespan opens it
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    add_problem_handler(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(extract.router)
    app.include_router(records.router)
    return app


app = create_app()
