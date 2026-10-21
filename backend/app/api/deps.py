"""FastAPI dependencies: the DB pool, the clock, and the Origin check.

The site has no sign-in (removed 21.10): anyone with the link can use it.

Owner: B
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from app.api.errors import ProblemError
from app.settings import Settings, get_settings

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def utc_now() -> datetime:
    """The clock, as a dependency so tests can move it."""
    return datetime.now(UTC)


def get_pool(request: Request) -> AsyncConnectionPool:
    """The app's pool (main.py lifespan). Not configured: 503, never a crash."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise ProblemError(503, "database_unavailable", "מסד הנתונים לא זמין כרגע")
    return pool


def same_origin(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """A request that changes data must come from our own page, so another site's
    page can't send changes through a visitor's browser. Browsers always send
    Origin on POST, PATCH and DELETE."""
    if request.method in _SAFE_METHODS:
        return
    if request.headers.get("origin") != settings.frontend_origin:
        raise ProblemError(403, "origin_not_allowed", "הבקשה לא הגיעה מהאתר של המערכת")
