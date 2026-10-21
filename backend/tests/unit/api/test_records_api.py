"""The records endpoints over HTTP, against a real Postgres (Dev-B plan B1.5).
The logic itself is tested in tests/unit/storage/test_review.py."""

import asyncio
import codecs
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.clock import israel_today
from app.extraction.provider import PageImage
from app.main import create_app
from app.rules.engine import apply_rules
from app.schemas.api import Form
from app.settings import Settings, get_settings
from app.storage.service import save_extracted_page

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"
ORIGIN = "http://localhost:5173"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


@pytest.fixture
def records(db):
    """Two forms: "clean" ready to approve, "no_commitment" with a flagged field."""

    async def go():
        saved = []
        for file_id, name in [("f1", "clean"), ("f2", "no_commitment")]:
            text = (FIXTURES / f"{name}.json").read_text(encoding="utf-8")
            form = Form.model_validate_json(text).model_copy(update={"file_id": file_id})
            form = apply_rules(form, today=date(2026, 10, 19))
            image = PageImage(
                file_id=file_id,
                filename=form.source_file,
                page_number=form.page_number,
                rotation=0,
                jpeg=b"jpeg",
            )
            async with await db.connect_async() as conn:
                saved += await save_extracted_page(conn, form, [image], now=NOW)
        ready, flagged = saved
        return {"ready": ready, "flagged": flagged}

    return db.run(go())


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


@pytest.fixture
def api(client, records):
    """The client, with the two records saved."""
    return client


def test_list_and_get(api, records):
    listed = api.get("/api/v1/records", params={"needs_review": "true"})
    assert listed.status_code == 200
    assert [item["record_id"] for item in listed.json()["items"]] == [records["flagged"].record_id]
    assert listed.json()["counts"] == {"pending": 2, "approved": 0, "needs_review": 1}

    record = api.get(f"/api/v1/records/{records['ready'].record_id}")
    assert record.status_code == 200
    assert record.json()["fields"]["national_id"]["value"] == "011223344"


def test_an_unknown_record_is_a_404_problem(api):
    response = api.get("/api/v1/records/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "not_found"


def test_patch_then_a_stale_version_is_a_409(api, records):
    ready = records["ready"]
    url = f"/api/v1/records/{ready.record_id}"
    body = {"version": ready.version, "fields": {"sender": {"value": "מכבי"}}}

    first = api.patch(url, json=body)
    assert first.status_code == 200
    assert first.json()["record"]["version"] == ready.version + 1

    stale = api.patch(url, json=body)
    assert stale.status_code == 409
    assert stale.json()["type"] == "version_conflict"


def test_approve_lists_the_blocking_fields(api, records):
    flagged = records["flagged"]
    response = api.post(
        f"/api/v1/records/{flagged.record_id}/approve", json={"version": flagged.version}
    )
    assert response.status_code == 409
    assert response.json()["type"] == "review_required"
    assert response.json()["blocking_fields"] == ["commitment_number"]


def test_approve_all_ready(api, records):
    items = [{"record_id": r.record_id, "version": r.version} for r in records.values()]
    response = api.post("/api/v1/records/approve", json={"items": items})

    assert response.status_code == 200
    assert [r["record_id"] for r in response.json()["approved"]] == [records["ready"].record_id]
    assert response.json()["skipped"][0]["type"] == "review_required"


def test_delete_answers_no_content(api, records):
    url = f"/api/v1/records/{records['flagged'].record_id}"
    assert api.delete(url).status_code == 204
    assert api.get(url).status_code == 404


def test_export_csv_is_a_download_of_the_filtered_records(api, records):
    response = api.get("/api/v1/records/export", params={"format": "csv", "needs_review": "false"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="records-{israel_today().isoformat()}.csv"'
    )
    assert response.headers["cache-control"] == "no-store"
    assert response.content.startswith(codecs.BOM_UTF8)
    lines = response.content.decode("utf-8-sig").splitlines()
    assert len(lines) == 2  # the header and the one ready record
    assert "011223344" in lines[1]


def test_export_json_is_the_list_of_records(api, records):
    response = api.get("/api/v1/records/export", params={"format": "json"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"].endswith(f'{israel_today().isoformat()}.json"')
    assert {r["record_id"] for r in response.json()} == {r.record_id for r in records.values()}


def test_export_needs_a_known_format(api):
    response = api.get("/api/v1/records/export", params={"format": "xlsx"})
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/records"),
        ("get", "/api/v1/records/r1"),
        ("get", "/api/v1/records/export?format=csv"),
        ("patch", "/api/v1/records/r1"),
        ("post", "/api/v1/records/r1/approve"),
        ("post", "/api/v1/records/approve"),
        ("delete", "/api/v1/records/r1"),
    ],
)
def test_every_records_endpoint_is_open_without_signing_in(api, method, path):
    # No sign-in (21.10): nothing answers 401.
    response = api.request(method, path, json={"version": 1})
    assert response.status_code != 401


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("patch", "/api/v1/records/r1"),
        ("post", "/api/v1/records/r1/approve"),
        ("post", "/api/v1/records/approve"),
        ("delete", "/api/v1/records/r1"),
    ],
)
def test_a_change_from_another_site_is_refused(api, method, path):
    response = api.request(
        method, path, json={"version": 1}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert response.json()["type"] == "origin_not_allowed"
