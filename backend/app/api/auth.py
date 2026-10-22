"""Login, logout and the signed-in user (Dev-B plan 2.6).

The session lives in an HttpOnly cookie, so the page's JavaScript never sees it.
A wrong username and a wrong password get the same answer.

Owner: B
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from psycopg_pool import AsyncConnectionPool

from app.api.deps import SESSION_COOKIE, get_pool, require_user, same_origin, utc_now
from app.api.errors import ProblemError, Responses
from app.auth import sessions
from app.auth.passwords import dummy_hash, verify_password
from app.schemas.api import LoginRequest, Problem, User
from app.settings import Settings, get_settings

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_UNAUTHENTICATED: Responses = {
    401: {"model": Problem, "description": 'No valid session ("unauthenticated")'}
}
_FOREIGN_ORIGIN: Responses = {
    403: {"model": Problem, "description": 'Not from our page ("origin_not_allowed")'}
}


@router.post(
    "/login",
    responses={
        401: {
            "model": Problem,
            "description": 'Wrong username or password ("invalid_credentials")',
        },
        429: {
            "model": Problem,
            "description": 'Locked after 5 failed logins ("too_many_attempts"), see Retry-After',
        },
        **_FOREIGN_ORIGIN,
    },
)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    pool: Annotated[AsyncConnectionPool, Depends(get_pool)],
    settings: Annotated[Settings, Depends(get_settings)],
    now: Annotated[datetime, Depends(utc_now)],
) -> User:
    """Sign in and set the session cookie (HttpOnly, Secure, SameSite=Strict)."""
    same_origin(request, settings)
    # Decide inside the transaction, answer after it: a failed attempt must be committed.
    async with pool.connection() as conn, conn.transaction():
        row = await sessions.user_for_login(conn, body.username)
        if row and row["locked_until"] and row["locked_until"] > now:
            retry_after = int((row["locked_until"] - now).total_seconds()) + 1
            outcome = "locked"
        elif row and row["is_active"] and verify_password(body.password, row["password_hash"]):
            await sessions.record_login(conn, row["id"], now)
            token = await sessions.create_session(conn, row["id"], now)
            user = User(id=row["id"], username=row["username"], display_name=row["display_name"])
            outcome = "ok"
        else:
            if row is None:
                verify_password(body.password, dummy_hash())  # same time as a real check
            else:
                await sessions.record_failed_login(conn, row["id"], now)
            outcome = "failed"

    if outcome == "locked":
        raise ProblemError(
            429,
            "too_many_attempts",
            "יותר מדי ניסיונות כניסה. אפשר לנסות שוב בעוד רבע שעה",
            headers={"Retry-After": str(retry_after)},
        )
    if outcome == "failed":
        raise ProblemError(401, "invalid_credentials", "שם המשתמש או הסיסמה שגויים")
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, secure=True, samesite="strict", path="/"
    )
    return user


@router.post("/logout", status_code=204, responses=_FOREIGN_ORIGIN)
async def logout(
    request: Request,
    response: Response,
    pool: Annotated[AsyncConnectionPool, Depends(get_pool)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> None:
    """End the session on the server too, so the token is useless even if it leaked."""
    same_origin(request, settings)
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        async with pool.connection() as conn:
            await sessions.revoke_session(conn, token)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")


@router.get("/me", responses=_UNAUTHENTICATED)
async def me(user: Annotated[User, Depends(require_user)]) -> User:
    """The signed-in user. The app calls it on load to decide: login screen or app."""
    return user
