"""The records routes take what the screen sends, before they are implemented.

The handlers answer 501 for now, so a 501 means the request got past validation
and reached the right handler. The session check is replaced by a fixed user:
login itself is tested in tests/unit/auth/.

Owner: shared
"""

from typing import get_args

import pytest
from fastapi.testclient import TestClient

from app.auth.deps import require_user
from app.main import app
from app.schemas import api

PATHS = app.openapi()["paths"]
client = TestClient(app)


@pytest.fixture(autouse=True)
def signed_in():
    app.dependency_overrides[require_user] = lambda: api.User(
        id="u1", username="tester", display_name="Tester"
    )
    yield
    app.dependency_overrides.pop(require_user, None)


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
    assert client.get("/api/v1/records", params={"form_type": form_type}).status_code == 501


def test_list_rejects_an_unknown_form_type():
    assert client.get("/api/v1/records", params={"form_type": "clalit"}).status_code == 422
