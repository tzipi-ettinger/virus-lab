"""One password for the whole site (D22)."""

import base64
import logging

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings, get_settings

PASSWORD = "סיסמה-ארוכה-17"


@pytest.fixture
def dist(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    return dist


def client_for(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="", **settings)))


def locked(**settings) -> TestClient:
    return client_for(site_password=PASSWORD, **settings)


def basic(username: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


RIGHT = basic("lab", PASSWORD)


def test_without_a_password_the_site_is_open():
    response = client_for().get("/api/v1/records")

    assert response.status_code == 503  # no database here, but not asked for a password


def test_an_api_call_without_the_password_is_refused():
    response = locked().get("/api/v1/records")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == 'Basic realm="virus-lab", charset="UTF-8"'
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "unauthorized"


def test_the_refusal_has_the_security_headers_and_is_not_cached():
    response = locked().get("/api/v1/records")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "no-store"


def test_the_right_password_lets_the_request_through():
    response = locked().get("/api/v1/records", headers=RIGHT)

    assert response.status_code == 503  # reached the route: no database here


def test_a_change_needs_the_password_before_the_origin_check():
    response = locked().delete("/api/v1/records/x", headers={"Origin": "https://evil.example"})

    assert response.status_code == 401


def test_the_page_itself_needs_the_password(dist):
    client = locked(static_dir=str(dist))

    assert client.get("/").status_code == 401
    assert client.get("/records/r1").status_code == 401
    assert client.get("/", headers=RIGHT).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        basic("lab", "wrong"),
        basic("someone", PASSWORD),
        basic("lab", PASSWORD + "x"),
        {"Authorization": "Bearer " + RIGHT["Authorization"].removeprefix("Basic ")},
        {"Authorization": "Basic not-base64!"},
        {"Authorization": "Basic " + base64.b64encode(b"no-colon").decode()},
        {"Authorization": "Basic"},
        {"Authorization": ""},
    ],
)
def test_anything_but_the_right_username_and_password_is_refused(headers):
    assert locked().get("/api/v1/records", headers=headers).status_code == 401


def test_the_username_can_be_changed():
    client = locked(site_username="virology")

    assert client.get("/api/v1/records", headers=basic("virology", PASSWORD)).status_code == 503
    assert client.get("/api/v1/records", headers=RIGHT).status_code == 401


def test_health_stays_open_for_render_and_the_keep_alive():
    settings = Settings(_env_file=None, database_url="", site_password=PASSWORD)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["site_password"] is True
    assert PASSWORD not in response.text


def test_the_password_never_shows_in_the_settings():
    settings = Settings(_env_file=None, site_password=PASSWORD)

    assert PASSWORD not in repr(settings)
    assert PASSWORD not in settings.model_dump_json()


def test_the_live_server_warns_when_the_site_is_open(caplog):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        client_for(env="production")

    assert "SITE_PASSWORD is not set" in caplog.text


def test_no_warning_when_the_live_server_has_a_password(caplog):
    with caplog.at_level(logging.WARNING, logger="app.main"):
        locked(env="production")

    assert "SITE_PASSWORD" not in caplog.text
