"""Login, logout, me and require_user, against a real Postgres (Dev-B plan B1.4)."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.deps import utc_now
from app.auth.passwords import hash_password
from app.main import create_app
from app.settings import Settings, get_settings

ORIGIN = "http://localhost:5173"
PASSWORD = "correct horse battery"
START = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def user(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', %s, 'דנה', %s)",
            (hash_password(PASSWORD), START),
        )


def make_client(settings, clock):
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[utc_now] = lambda: clock.now
    # https: the session cookie is Secure. A selector loop: psycopg async can't use Proactor.
    return TestClient(
        app,
        base_url="https://testserver",
        headers={"Origin": ORIGIN},
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    )


@pytest.fixture
def client(db, clock):
    with make_client(Settings(_env_file=None, database_url=db.url), clock) as client:
        yield client


def login(client, username="dana", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"username": username, "password": password})


def test_login_returns_the_user_and_sets_a_safe_cookie(client, user):
    response = login(client)

    assert response.status_code == 200
    assert response.json() == {"id": "u1", "username": "dana", "display_name": "דנה"}
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("session=")
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert flag in cookie


def test_me_after_login(client, user):
    login(client)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 200
    assert response.json()["username"] == "dana"


def test_me_without_a_session_is_401_problem(client, user):
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "unauthenticated"


def test_records_need_a_session(client, user):
    assert client.get("/api/v1/records").status_code == 401


def test_wrong_password_and_unknown_user_get_the_same_answer(client, user):
    wrong_password = login(client, password="wrong password!")
    unknown_user = login(client, username="nobody")

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["type"] == "invalid_credentials"


def test_sixth_failed_login_is_locked_even_with_the_right_password(client, user):
    for _ in range(5):
        assert login(client, password="wrong password!").status_code == 401

    response = login(client)

    assert response.status_code == 429
    assert response.json()["type"] == "too_many_attempts"
    assert int(response.headers["retry-after"]) == 15 * 60 + 1


def test_lock_ends_after_15_minutes(client, clock, user):
    for _ in range(5):
        login(client, password="wrong password!")

    clock.advance(minutes=15, seconds=1)

    assert login(client).status_code == 200


def test_a_successful_login_resets_the_count(client, user):
    for _ in range(4):
        login(client, password="wrong password!")
    login(client)

    for _ in range(4):
        assert login(client, password="wrong password!").status_code == 401
    assert login(client).status_code == 200


def test_logout_ends_the_session_on_the_server(client, user, db):
    login(client)
    token = client.cookies["session"]

    assert client.post("/api/v1/auth/logout").status_code == 204

    assert client.get("/api/v1/auth/me").status_code == 401
    client.cookies.set("session", token)  # the old token, replayed
    assert client.get("/api/v1/auth/me").status_code == 401
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"] == 0


def test_only_a_hash_of_the_token_is_stored(client, user, db):
    login(client)
    token = client.cookies["session"]

    with db.connect() as conn:
        [row] = conn.execute("SELECT token_hash FROM sessions").fetchall()

    assert row["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in row["token_hash"]


def test_session_expires_after_8_idle_hours(client, clock, user):
    login(client)

    clock.advance(hours=8, seconds=1)

    assert client.get("/api/v1/auth/me").status_code == 401


def test_each_request_keeps_the_session_alive(client, clock, user):
    login(client)

    for _ in range(3):
        clock.advance(hours=7)
        assert client.get("/api/v1/auth/me").status_code == 200


def test_inactive_user_cannot_login_or_use_a_session(client, user, db):
    login(client)
    with db.connect() as conn:
        conn.execute("UPDATE users SET is_active = FALSE")

    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401


@pytest.mark.parametrize("origin", ["https://evil.example", None])
def test_login_from_another_origin_is_refused(client, user, origin):
    headers = {"Origin": origin} if origin else {}
    client.headers.pop("Origin")

    response = client.post(
        "/api/v1/auth/login", json={"username": "dana", "password": PASSWORD}, headers=headers
    )

    assert response.status_code == 403
    assert response.json()["type"] == "origin_not_allowed"


def test_logout_from_another_origin_is_refused(client, user):
    login(client)

    response = client.post("/api/v1/auth/logout", headers={"Origin": "https://evil.example"})

    assert response.status_code == 403
    assert client.get("/api/v1/auth/me").status_code == 200


def test_without_database_url_login_is_503(clock):
    with make_client(Settings(_env_file=None), clock) as client:
        response = login(client)

    assert response.status_code == 503
    assert response.json()["type"] == "database_unavailable"
