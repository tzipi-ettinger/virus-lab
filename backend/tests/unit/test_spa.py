"""The built frontend is served next to the API, on one origin (app/spa.py)."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

INDEX = "<!doctype html><title>virus-lab</title>"


@pytest.fixture
def dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(INDEX, encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("not for the browser", encoding="utf-8")
    return dist


def client_for(static_dir: str) -> TestClient:
    # No `with`: the lifespan (the DB pool) doesn't run, and isn't needed here.
    return TestClient(create_app(Settings(_env_file=None, static_dir=static_dir)))


@pytest.mark.parametrize("path", ["/", "/records", "/records/r_123", "/nope"])
def test_app_paths_get_the_page(dist, path):
    response = client_for(str(dist)).get(path)

    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["cache-control"] == "no-cache"


def test_assets_are_served(dist):
    response = client_for(str(dist)).get("/assets/index-abc123.js")

    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]


def test_files_at_the_top_of_dist_are_served(dist):
    response = client_for(str(dist)).get("/favicon.svg")

    assert response.status_code == 200
    assert response.text == "<svg/>"


@pytest.mark.parametrize("path", ["/api", "/api/nope", "/api/v1/nope"])
def test_unknown_api_path_is_a_json_404_not_the_page(dist, path):
    response = client_for(str(dist)).get(path)

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "not_found"


def test_api_still_answers(dist):
    response = client_for(str(dist)).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_head_works_for_a_quick_check(dist):
    assert client_for(str(dist)).head("/").status_code == 200


def test_files_outside_dist_are_never_served(dist):
    response = client_for(str(dist)).get("/%2e%2e/secret.txt")

    assert "not for the browser" not in response.text


def test_without_static_dir_nothing_is_served():
    client = client_for("")

    assert client.get("/records").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_static_dir_without_a_build_refuses_to_start(tmp_path):
    with pytest.raises(RuntimeError, match="Build the frontend"):
        client_for(str(tmp_path))
