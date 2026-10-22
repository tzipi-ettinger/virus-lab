"""All SQL for users and sessions: login attempts, lockout, and session tokens.

The browser holds a random token; the DB holds only its SHA-256, so a leaked
sessions table opens no session.

Owner: B
"""

import hashlib
import secrets
from datetime import datetime, timedelta

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from app.schemas.api import User

SESSION_IDLE = timedelta(hours=8)  # D8: signed out after 8 hours without a request
MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def user_for_login(conn: AsyncConnection, username: str) -> dict | None:
    """The user's row, locked until the transaction ends, so two wrong passwords
    at once both count."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT id, username, display_name, password_hash, is_active, locked_until"
            " FROM users WHERE username = %s FOR UPDATE",
            (username,),
        )
        return await cur.fetchone()


async def record_failed_login(conn: AsyncConnection, user_id: str, now: datetime) -> None:
    """The fifth failure in a row locks the user for LOCKOUT and starts the count again."""
    await conn.execute(
        "UPDATE users SET"
        " locked_until = CASE WHEN failed_attempts + 1 >= %(max)s"
        "  THEN %(until)s ELSE locked_until END,"
        " failed_attempts = CASE WHEN failed_attempts + 1 >= %(max)s"
        "  THEN 0 ELSE failed_attempts + 1 END"
        " WHERE id = %(id)s",
        {"max": MAX_FAILED_LOGINS, "until": now + LOCKOUT, "id": user_id},
    )


async def record_login(conn: AsyncConnection, user_id: str, now: datetime) -> None:
    await conn.execute(
        "UPDATE users SET failed_attempts = 0, locked_until = NULL, last_login_at = %s"
        " WHERE id = %s",
        (now, user_id),
    )


async def create_session(conn: AsyncConnection, user_id: str, now: datetime) -> str:
    """A new session; returns the token for the cookie. Expired sessions are cleared here."""
    await conn.execute("DELETE FROM sessions WHERE expires_at <= %s", (now,))
    token = secrets.token_urlsafe(32)
    await conn.execute(
        "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at)"
        " VALUES (%s, %s, %s, %s, %s)",
        (token_hash(token), user_id, now, now + SESSION_IDLE, now),
    )
    return token


async def user_for_session(conn: AsyncConnection, token: str, now: datetime) -> User | None:
    """The session's user, if it hasn't expired and the user is active. Each use
    moves the expiry SESSION_IDLE ahead."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "UPDATE sessions s SET last_seen_at = %(now)s, expires_at = %(expires)s"
            " FROM users u"
            " WHERE s.token_hash = %(hash)s AND s.expires_at > %(now)s"
            " AND u.id = s.user_id AND u.is_active"
            " RETURNING u.id, u.username, u.display_name",
            {"now": now, "expires": now + SESSION_IDLE, "hash": token_hash(token)},
        )
        row = await cur.fetchone()
    return User(**row) if row else None


async def revoke_session(conn: AsyncConnection, token: str) -> None:
    await conn.execute("DELETE FROM sessions WHERE token_hash = %s", (token_hash(token),))
