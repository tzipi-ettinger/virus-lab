"""Hardening for the live server (Dev-B plan B2.2)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.security import CSP
from app.settings import Settings


@pytest.fixture
def dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("1", encoding="utf-8")
    return dist


def client_for(**settings) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, database_url="", **settings)))


ALWAYS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "content-security-policy": CSP,
}


@pytest.mark.parametrize("path", ["/api/health", "/", "/records/r1", "/assets/app.js"])
def test_every_response_has_the_security_headers(dist, path):
    response = client_for(static_dir=str(dist)).get(path)

    assert response.status_code == 200
    for name, value in ALWAYS.items():
        assert response.headers[name] == value


def test_error_answers_have_them_too():
    response = client_for().get("/api/v1/records")  # no session

    assert response.status_code in (401, 503)
    assert response.headers["x-content-type-options"] == "nosniff"


def test_api_answers_are_never_cached(dist):
    client = client_for(static_dir=str(dist))

    assert client.get("/api/health").headers["cache-control"] == "no-store"
    assert client.get("/assets/app.js").headers.get("cache-control") != "no-store"


def test_hsts_only_in_production():
    assert "strict-transport-security" not in client_for().get("/api/health").headers
    hsts = client_for(env="production").get("/api/health").headers["strict-transport-security"]
    assert hsts.startswith("max-age=")


def test_dev_docs_page_is_left_without_csp_so_it_loads():
    response = client_for().get("/docs")

    assert response.status_code == 200
    assert "content-security-policy" not in response.headers
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off_in_production(path):
    assert client_for().get(path).status_code == 200
    assert client_for(env="production").get(path).status_code == 404


def test_the_contract_is_still_built_in_production():
    app = create_app(Settings(_env_file=None, database_url="", env="production"))

    assert "/api/v1/records" in app.openapi()["paths"]
