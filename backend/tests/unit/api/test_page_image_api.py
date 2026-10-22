"""GET /api/v1/pages/{page_id}/image against a real Postgres, signed in through
the real login (Dev-B plan B1.5)."""

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.main import create_app
from app.settings import Settings, get_settings

ORIGIN = "http://localhost:5173"
PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0 not really a jpeg \xff\xd9"


@pytest.fixture
def saved_page(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', %s, 'דנה', %s)",
            (hash_password(PASSWORD), NOW),
        )
        conn.execute(
            "INSERT INTO page (id, file_id, source_filename, page_number, created_at, created_by)"
            " VALUES ('p1', 'f1', 'a.pdf', 1, %s, 'u1')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO page_image (page_id, mime, sha256, bytes)"
            " VALUES ('p1', 'image/jpeg', %s, %s)",
            (hashlib.sha256(JPEG).hexdigest(), JPEG),
        )
    return "p1"


@pytest.fixture
def client(db):
    settings = Settings(_env_file=None, database_url=db.url)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    # https: the session cookie is Secure. A selector loop: psycopg async can't use Proactor.
    with TestClient(
        app,
        base_url="https://testserver",
        headers={"Origin": ORIGIN},
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        yield client


def login(client):
    response = client.post("/api/v1/auth/login", json={"username": "dana", "password": PASSWORD})
    assert response.status_code == 200


def test_serves_the_saved_jpeg_without_caching(client, saved_page):
    login(client)
    response = client.get(f"/api/v1/pages/{saved_page}/image")

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"


def test_an_unknown_page_is_a_404_problem(client, saved_page):
    login(client)
    response = client.get("/api/v1/pages/nope/image")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "page_not_found"


def test_needs_a_signed_in_user(client, saved_page):
    response = client.get(f"/api/v1/pages/{saved_page}/image")

    assert response.status_code == 401
    assert JPEG not in response.content
