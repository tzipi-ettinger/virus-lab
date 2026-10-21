"""GET /api/v1/pages/{page_id}/image against a real Postgres (Dev-B plan B1.5)."""

import asyncio
import hashlib
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings, get_settings

ORIGIN = "http://localhost:5173"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0 not really a jpeg \xff\xd9"


@pytest.fixture
def saved_page(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO page (id, file_id, source_filename, page_number, created_at)"
            " VALUES ('p1', 'f1', 'a.pdf', 1, %s)",
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
    # A selector loop: psycopg async can't use Proactor.
    with TestClient(
        app,
        headers={"Origin": ORIGIN},
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        yield client


def test_serves_the_saved_jpeg_without_caching(client, saved_page):
    response = client.get(f"/api/v1/pages/{saved_page}/image")

    assert response.status_code == 200
    assert response.content == JPEG
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "no-store"


def test_an_unknown_page_is_a_404_problem(client, saved_page):
    response = client.get("/api/v1/pages/nope/image")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "page_not_found"
