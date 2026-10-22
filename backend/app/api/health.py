"""GET /api/health.

Also says which extraction provider is on, how many Gemini keys it has, and
whether the dev cache is in front of it, so a deploy can be checked in a browser:
a live server answering with "fake" would serve fixtures that look like real
readings, and one with the cache on would keep patients' readings on its disk.
The number of keys, never a key: a server showing 1 has not picked up
GEMINI_API_KEYS.

It checks the database too, since Render's health check (render.yaml) calls this
path: a server whose database is down answers 503, so Render doesn't call it
healthy. Without DATABASE_URL (locally, the CI image check) the database is "off"
and the answer is still 200.

Owner: A
"""

import asyncio
import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response
from psycopg_pool import AsyncConnectionPool

from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Short: Render's own health check gives up after a few seconds.
DB_CHECK_TIMEOUT_S = 3.0

DatabaseState = Literal["ok", "off", "unavailable"]


@router.get(
    "/api/health",
    responses={
        503: {"description": 'The database is set but does not answer ("database": "unavailable")'}
    },
)
async def health(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str | bool | int]:
    database = await _database_state(getattr(request.app.state, "pool", None))
    if database == "unavailable":
        response.status_code = 503
    return {
        "status": "error" if database == "unavailable" else "ok",
        "database": database,
        "extraction_provider": settings.extraction_provider,
        # What get_provider does, not just the setting: the cache is only ever in
        # front of Gemini.
        "extraction_cache": settings.extraction_cache and settings.extraction_provider == "gemini",
        # Only Gemini reads with keys; fake has none, whatever .env holds.
        "gemini_keys": len(settings.gemini_keys())
        if settings.extraction_provider == "gemini"
        else 0,
    }


async def _database_state(pool: AsyncConnectionPool | None) -> DatabaseState:
    """Whether the database answers SELECT 1 in time; "off" without DATABASE_URL."""
    if pool is None:
        return "off"
    try:
        async with asyncio.timeout(DB_CHECK_TIMEOUT_S), pool.connection() as conn:
            await conn.execute("SELECT 1")
    except Exception as exc:
        # The type only: a connection error can quote the URL, which holds the password.
        logger.warning("health: database check failed (%s)", type(exc).__name__)
        return "unavailable"
    return "ok"
