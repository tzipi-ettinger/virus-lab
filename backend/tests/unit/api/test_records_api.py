"""The records endpoints over HTTP, against a real Postgres and the real login
(Dev-B plan B1.5). The logic itself is tested in tests/unit/storage/test_review.py."""

import asyncio
import codecs
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.clock import israel_today
from app.extraction.provider import PageImage
from app.main import create_app
from app.rules.engine import apply_rules
from app.schemas.api import Form, User
from app.settings import Settings, get_settings
from app.storage.service import save_extracted_page

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"
ORIGIN = "http://localhost:5173"
PASSWORD = "correct horse battery"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
USER = User(id="u1", username="dana", display_name="דנה")


@pytest.fixture
def records(db):
    """Two forms: "clean" ready to approve, "no_commitment" with a flagged field."""
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', %s, 'דנה', %s)",
            (hash_password(PASSWORD), NOW),
        )

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
                saved += await save_extracted_page(conn, form, [image], USER, now=NOW)
        ready, flagged = saved
        return {"ready": ready, "flagged": flagged}

    return db.run(go())


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


@pytest.fixture
def signed_in(client, records):
    response = client.post("/api/v1/auth/login", json={"username": "dana", "password": PASSWORD})
    assert response.status_code == 200
    return client


def test_list_and_get(signed_in, records):
    listed = signed_in.get("/api/v1/records", params={"needs_review": "true"})
    assert listed.status_code == 200
    assert [item["record_id"] for item in listed.json()["items"]] == [records["flagged"].record_id]
    assert listed.json()["counts"] == {"pending": 2, "approved": 0, "needs_review": 1}

    record = signed_in.get(f"/api/v1/records/{records['ready'].record_id}")
    assert record.status_code == 200
    assert record.json()["fields"]["national_id"]["value"] == "011223344"


def test_an_unknown_record_is_a_404_problem(signed_in):
    response = signed_in.get("/api/v1/records/nope")
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "not_found"


def test_patch_then_a_stale_version_is_a_409(signed_in, records):
    ready = records["ready"]
    url = f"/api/v1/records/{ready.record_id}"
    body = {"version": ready.version, "fields": {"sender": {"value": "מכבי"}}}

    first = signed_in.patch(url, json=body)
    assert first.status_code == 200
    assert first.json()["record"]["version"] == ready.version + 1

    stale = signed_in.patch(url, json=body)
    assert stale.status_code == 409
    assert stale.json()["type"] == "version_conflict"


def test_approve_lists_the_blocking_fields(signed_in, records):
    flagged = records["flagged"]
    response = signed_in.post(
        f"/api/v1/records/{flagged.record_id}/approve", json={"version": flagged.version}
    )
    assert response.status_code == 409
    assert response.json()["type"] == "review_required"
    assert response.json()["blocking_fields"] == ["commitment_number"]


def test_approve_all_ready(signed_in, records):
    items = [{"record_id": r.record_id, "version": r.version} for r in records.values()]
    response = signed_in.post("/api/v1/records/approve", json={"items": items})

    assert response.status_code == 200
    assert [r["record_id"] for r in response.json()["approved"]] == [records["ready"].record_id]
    assert response.json()["skipped"][0]["type"] == "review_required"


def test_delete_answers_no_content(signed_in, records):
    url = f"/api/v1/records/{records['flagged'].record_id}"
    assert signed_in.delete(url).status_code == 204
    assert signed_in.get(url).status_code == 404


def test_export_csv_is_a_download_of_the_filtered_records(signed_in, records):
    response = signed_in.get(
        "/api/v1/records/export", params={"format": "csv", "needs_review": "false"}
    )

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


def test_export_json_is_the_list_of_records(signed_in, records):
    response = signed_in.get("/api/v1/records/export", params={"format": "json"})

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.headers["content-disposition"].endswith(f'{israel_today().isoformat()}.json"')
    assert {r["record_id"] for r in response.json()} == {r.record_id for r in records.values()}


def test_export_needs_a_known_format(signed_in):
    response = signed_in.get("/api/v1/records/export", params={"format": "xlsx"})
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
def test_every_records_endpoint_needs_a_session(client, method, path):
    response = client.request(method, path, json={"version": 1})
    assert response.status_code == 401


def test_the_history_says_who_did_what_and_when(signed_in, records):
    ready = records["ready"]
    url = f"/api/v1/records/{ready.record_id}"
    patched = signed_in.patch(
        url, json={"version": ready.version, "fields": {"sender": {"value": "מכבי"}}}
    )
    signed_in.post(f"{url}/approve", json={"version": patched.json()["record"]["version"]})

    response = signed_in.get(f"{url}/history")

    assert response.status_code == 200
    events = response.json()
    assert [(e["action"], e["field"]) for e in events] == [
        ("created", None),
        ("corrected", "sender"),
        ("approved", None),
    ]
    assert {(e["username"], e["display_name"]) for e in events} == {("dana", "דנה")}
    assert "מכבי" not in response.text  # never the values (D13)


def test_the_history_of_an_unknown_record_is_a_404(signed_in):
    response = signed_in.get("/api/v1/records/nope/history")
    assert response.status_code == 404
    assert response.json()["type"] == "not_found"


def test_the_history_needs_sign_in(client, records):
    response = client.get(f"/api/v1/records/{records['ready'].record_id}/history")
    assert response.status_code == 401


def test_stats(signed_in, records):
    response = signed_in.get("/api/v1/stats")
    assert response.status_code == 200
    stats = response.json()
    assert (stats["pending"], stats["approved"], stats["needs_review"]) == (2, 0, 1)
    assert stats["fields_flagged"] >= 1
    assert stats["by_field"] == []


def test_stats_need_sign_in(client, records):
    assert client.get("/api/v1/stats").status_code == 401
