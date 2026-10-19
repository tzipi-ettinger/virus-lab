"""FastAPI dependencies: the DB pool, the clock, and require_user.

Put `user: Annotated[User, Depends(require_user)]` on any endpoint that needs a
signed-in user. Tests skip it with `app.dependency_overrides[require_user]`.

Owner: B
"""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from psycopg_pool import AsyncConnectionPool

from app.api.errors import ProblemError
from app.auth import sessions
from app.schemas.api import User
from app.settings import Settings, get_settings

SESSION_COOKIE = "session"
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def utc_now() -> datetime:
    """The clock, as a dependency so tests can move it (lockout, session expiry)."""
    return datetime.now(UTC)


def get_pool(request: Request) -> AsyncConnectionPool:
    """The app's pool (main.py lifespan). Not configured: 503, never a crash."""
    pool = getattr(request.app.state, "pool", None)
    if pool is None:
        raise ProblemError(503, "database_unavailable", "מסד הנתונים לא זמין כרגע")
    return pool


def check_origin(request: Request, settings: Settings) -> None:
    """CSRF (Dev-B plan 2.6): a request that changes data must come from our own
    page. Browsers always send Origin on POST, PATCH and DELETE."""
    if request.method in _SAFE_METHODS:
        return
    if request.headers.get("origin") != settings.frontend_origin:
        raise ProblemError(403, "origin_not_allowed", "הבקשה לא הגיעה מהאתר של המערכת")


async def require_user(
    request: Request,
    pool: Annotated[AsyncConnectionPool, Depends(get_pool)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Annotated[datetime, Depends(utc_now)],
) -> User:
    """The signed-in user, or 401. Also checks Origin on a request that changes data.

    Takes its own short connection, so a long request (an upload) doesn't hold one.
    """
    check_origin(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    user = None
    if token:
        async with pool.connection() as conn:
            user = await sessions.user_for_session(conn, token, now)
    if user is None:
        raise ProblemError(401, "unauthenticated", "צריך להתחבר")
    return user
