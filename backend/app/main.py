"""create_app: routes, CORS, error handlers, the DB pool, and the built frontend.

Owner: A
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, extract, health, records
from app.api.errors import add_problem_handler
from app.keep_alive import start_keep_alive, stop_keep_alive
from app.pipeline.jobs import ExtractJobs
from app.security import (
    HideUnexpectedErrors,
    SecurityHeaders,
    keep_patient_data_out_of_server_logs,
)
from app.settings import Settings, get_settings
from app.spa import mount_spa
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
        keep_alive = start_keep_alive(settings.keep_alive_base_url, settings.keep_alive_interval_s)
        try:
            yield
        finally:
            await stop_keep_alive(keep_alive)
            # Before the pool closes: a job still running saves through it.
            await app.state.jobs.shutdown()
            if app.state.pool is not None:
                await app.state.pool.close()

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    keep_patient_data_out_of_server_logs()
    if settings.extraction_provider == "fake":
        logger.warning("EXTRACTION_PROVIDER=fake: every answer is a test fixture, not a reading")
    elif settings.extraction_cache:
        logger.warning(
            "EXTRACTION_CACHE=true: pages already read come from backend/.cache "
            "(dev only, sample files only)"
        )
    # The live server doesn't describe its API to strangers: no /docs, /redoc or
    # /openapi.json. scripts/export_openapi still builds the contract from the code.
    hidden: dict[str, Any] = {"docs_url": None, "redoc_url": None, "openapi_url": None}
    app = FastAPI(
        title="virus-lab",
        lifespan=_lifespan(settings),
        **(hidden if settings.production else {}),
    )
    app.state.pool = None  # until the lifespan opens it
    app.state.jobs = ExtractJobs()  # uploads read in the background (extract.py)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(HideUnexpectedErrors)
    # Added last, so it wraps everything: errors and CORS answers get the headers too.
    app.add_middleware(SecurityHeaders, production=settings.production)
    add_problem_handler(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(extract.router)
    app.include_router(records.router)
    if settings.static_dir:
        mount_spa(app, Path(settings.static_dir))  # last: it catches every other path
    return app


app = create_app()
