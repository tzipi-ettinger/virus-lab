"""create_app: routes, CORS, error handlers.

Owner: A
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import extract, health, records
from app.settings import get_settings

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.extraction_provider == "fake":
        logger.warning("EXTRACTION_PROVIDER=fake: every answer is a test fixture, not a reading")
    app = FastAPI(title="virus-lab")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(extract.router)
    app.include_router(records.router)
    return app


app = create_app()
