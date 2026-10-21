"""POST /api/v1/extract saves each form, against a real Postgres. The pipeline and
the response are tested in test_extract.py."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api import extract
from app.main import create_app
from app.settings import Settings, get_settings
from tests.unit.api.uploads import Answers, make_pdf, upload

ORIGIN = "http://localhost:5173"


class CountingAnswers(Answers):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def extract(self, page):
        self.calls += 1
        return await super().extract(page)


@pytest.fixture
def provider():
    return CountingAnswers()


@pytest.fixture
def client(db, provider):
    settings = Settings(_env_file=None, database_url=db.url)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[extract.get_provider] = lambda: provider
    # A selector loop: psycopg async can't use Proactor.
    with TestClient(
        app,
        headers={"Origin": ORIGIN},
        backend_options={"loop_factory": asyncio.SelectorEventLoop},
    ) as client:
        yield client


def saved_record_ids(db):
    with db.connect() as conn:
        return {row["id"] for row in conn.execute("SELECT id FROM record")}


def test_every_form_is_saved_as_pending_records(client, db):
    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(2))))

    assert response.status_code == 200
    records = response.json()["records"]
    assert len(records) == 2
    assert {r["status"] for r in records} == {"pending"}
    assert saved_record_ids(db) == {r["record_id"] for r in records}
    with db.connect() as conn:
        pages = conn.execute("SELECT source_filename, page_number FROM page").fetchall()
    assert sorted((p["source_filename"], p["page_number"]) for p in pages) == [
        ("a.pdf", 1),
        ("a.pdf", 2),
    ]


def test_the_saved_page_image_is_served_for_the_preview(client):
    extracted = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))
    record = extracted.json()["records"][0]

    response = client.get(f"/api/v1/pages/{record['page_id']}/image")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_an_upload_from_another_site_is_not_read_or_saved(client, db, provider):
    response = client.post(
        "/api/v1/extract",
        files=upload(("a.pdf", make_pdf(1))),
        headers={"Origin": "https://evil.example"},
    )

    assert response.status_code == 403
    assert response.json()["type"] == "origin_not_allowed"
    assert provider.calls == 0  # no quota spent on an upload that is refused
    assert saved_record_ids(db) == set()
