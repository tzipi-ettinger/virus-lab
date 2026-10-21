"""The records routes take what the screen sends.

No database here: the pool is a stub that raises Reached when a handler asks it
for a connection, so Reached means the request got past validation and reached
the right handler. What the handlers do is tested in tests/unit/api/. The Origin
check is turned off here: it is tested there too.

Owner: shared
"""

from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_pool, same_origin
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
def stub_pool():
    app.dependency_overrides[same_origin] = lambda: None
    app.dependency_overrides[get_pool] = StubPool
    yield
    app.dependency_overrides.pop(same_origin, None)
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
        "sort",
        "limit",
        "offset",
    } == set(list_params())


@pytest.mark.parametrize("form_type", get_args(api.FormType))
def test_list_filters_by_any_form_type(form_type):
    with pytest.raises(Reached):
        client.get("/api/v1/records", params={"form_type": form_type})


def test_list_rejects_an_unknown_form_type():
    assert client.get("/api/v1/records", params={"form_type": "clalit"}).status_code == 422


@pytest.mark.parametrize("sort", get_args(api.RecordSort))
def test_list_sorts_by_any_column_either_way(sort):
    with pytest.raises(Reached):
        client.get("/api/v1/records", params={"sort": sort})


@pytest.mark.parametrize("sort", ["id", "-search_text", "received_date; DROP TABLE record"])
def test_list_rejects_any_other_sort(sort):
    assert client.get("/api/v1/records", params={"sort": sort}).status_code == 422


def test_every_sort_key_has_both_directions():
    keys = get_args(api.RecordSort)
    assert {k for k in keys if not k.startswith("-")} == {k[1:] for k in keys if k.startswith("-")}


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
    with pytest.raises(Reached):
        client.get("/api/v1/records/export", params=params)


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
