"""POST /api/v1/extract saves each form, against a real Postgres, signed in through
the real login. The pipeline and the response are tested in test_extract.py."""

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.api import extract
from app.auth.passwords import hash_password
from app.main import create_app
from app.settings import Settings, get_settings
from tests.unit.api.test_extract import Answers, make_pdf, upload

ORIGIN = "http://localhost:5173"
PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


class CountingAnswers(Answers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def extract(self, page):
        self.calls += 1
        return await super().extract(page)


@pytest.fixture
def user(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', %s, 'דנה', %s)",
            (hash_password(PASSWORD), NOW),
        )


@pytest.fixture
def provider():
    return CountingAnswers()


@pytest.fixture
def client(db, provider):
    settings = Settings(_env_file=None, database_url=db.url)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[extract.get_provider] = lambda: provider
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


def saved_record_ids(db):
    with db.connect() as conn:
        return {row["id"] for row in conn.execute("SELECT id FROM record")}


def test_every_form_is_saved_as_pending_records_by_the_user(client, user, db):
    login(client)

    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(2))))

    assert response.status_code == 200
    records = response.json()["records"]
    assert len(records) == 2
    assert saved_record_ids(db) == {r["record_id"] for r in records}
    with db.connect() as conn:
        pages = conn.execute("SELECT source_filename, page_number, created_by FROM page").fetchall()
    assert sorted((p["source_filename"], p["page_number"], p["created_by"]) for p in pages) == [
        ("a.pdf", 1, "u1"),
        ("a.pdf", 2, "u1"),
    ]


def test_the_saved_page_image_is_served_for_the_preview(client, user):
    login(client)
    extracted = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))
    record = extracted.json()["records"][0]

    response = client.get(f"/api/v1/pages/{record['page_id']}/image")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_without_signing_in_nothing_is_read_or_saved(client, user, db, provider):
    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))

    assert response.status_code == 401
    assert response.json()["type"] == "unauthenticated"
    assert provider.calls == 0  # no quota spent on an upload that can't be saved
    assert saved_record_ids(db) == set()
