"""The records routes take what the screen sends.

No database here: the pool is a stub that raises Reached when a handler asks it
for a connection, so Reached means the request got past validation and reached
the right handler. What the handlers do is tested in tests/unit/api/. The session
check is replaced by a fixed user: login itself is tested in tests/unit/auth/.

Owner: shared
"""

from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import get_pool, require_user
from app.main import app
from app.schemas import api

PATHS = app.openapi()["paths"]
client = TestClient(app)


class Reached(Exception):
    pass


class StubPool:
    def connection(self):
        raise Reached


@pytest.fixture(autouse=True)
def signed_in():
    app.dependency_overrides[require_user] = lambda: api.User(
        id="u1", username="tester", display_name="Tester"
    )
    app.dependency_overrides[get_pool] = StubPool
    yield
    app.dependency_overrides.pop(require_user, None)
    app.dependency_overrides.pop(get_pool, None)


def list_params() -> dict[str, dict]:
    return {p["name"]: p for p in PATHS["/api/v1/records"]["get"]["parameters"]}


def test_list_takes_every_filter_of_the_screen():
    assert {
        "q",
        "status",
        "needs_review",
        "sender",
        "form_type",
        "date_from",
        "date_to",
        "limit",
        "offset",
    } == set(list_params())


@pytest.mark.parametrize("form_type", get_args(api.FormType))
def test_list_filters_by_any_form_type(form_type):
    with pytest.raises(Reached):
        client.get("/api/v1/records", params={"form_type": form_type})


def test_list_rejects_an_unknown_form_type():
    assert client.get("/api/v1/records", params={"form_type": "clalit"}).status_code == 422


def test_approve_many_reaches_its_own_route():
    body = {"items": [{"record_id": "r1", "version": 1}, {"record_id": "r2", "version": 3}]}
    with pytest.raises(Reached):
        client.post("/api/v1/records/approve", json=body)


@pytest.mark.parametrize("body", [{"items": []}, {"items": [{"record_id": "r1"}]}])
def test_approve_many_needs_records_with_versions(body):
    assert client.post("/api/v1/records/approve", json=body).status_code == 422


@pytest.mark.parametrize("export_format", ["csv", "json"])
def test_export_takes_a_format_and_the_filters(export_format):
    params = {"format": export_format, "status": "approved", "form_type": "hmo_form"}
    assert client.get("/api/v1/records/export", params=params).status_code == 501


@pytest.mark.parametrize("params", [{}, {"format": "xlsx"}])
def test_export_needs_csv_or_json(params):
    # A 422 also shows the request didn't land on GET /records/{record_id}.
    assert client.get("/api/v1/records/export", params=params).status_code == 422


def test_export_takes_the_same_filters_as_the_list():
    export_params = {p["name"] for p in PATHS["/api/v1/records/export"]["get"]["parameters"]}
    assert export_params == set(list_params()) - {"limit", "offset"} | {"format"}


def test_delete_record_answers_no_content():
    assert "204" in PATHS["/api/v1/records/{record_id}"]["delete"]["responses"]


def test_senders_lists_the_closed_list():
    response = client.get("/api/v1/senders")
    assert response.status_code == 200
    assert {"כללית", "מכבי", "מאוחדת", "לאומית"} <= set(response.json())


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/records"),
        ("get", "/api/v1/records/export"),
        ("post", "/api/v1/records/approve"),
        ("get", "/api/v1/records/{record_id}"),
        ("patch", "/api/v1/records/{record_id}"),
        ("delete", "/api/v1/records/{record_id}"),
        ("post", "/api/v1/records/{record_id}/approve"),
        ("get", "/api/v1/pages/{page_id}/image"),
        ("get", "/api/v1/senders"),
        ("post", "/api/v1/extract"),
    ],
)
def test_endpoint_is_in_the_contract(method, path):
    assert method in PATHS.get(path, {})
