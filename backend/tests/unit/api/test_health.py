from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings, get_settings


def client(**settings) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings)
    return TestClient(app)


def test_health_returns_ok_and_the_provider():
    response = client().get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "extraction_provider": "fake",
        "extraction_cache": False,
        "gemini_keys": 0,
        "site_password": False,
    }


def test_health_shows_when_the_server_reads_with_gemini():
    response = client(extraction_provider="gemini", gemini_api_key="k", gemini_model="m").get(
        "/api/health"
    )

    assert response.json()["extraction_provider"] == "gemini"
    assert "k" not in response.json().values()  # never the key


def test_health_counts_the_keys_but_never_shows_them():
    response = client(
        extraction_provider="gemini", gemini_api_keys="key-a,key-b,key-c", gemini_model="m"
    ).get("/api/health")

    assert response.json()["gemini_keys"] == 3
    assert "key-a" not in response.text


def test_health_shows_when_the_dev_cache_is_on():
    gemini = {"extraction_provider": "gemini", "gemini_api_key": "k", "gemini_model": "m"}

    assert client(**gemini, extraction_cache=True).get("/api/health").json()["extraction_cache"]
    assert not client(**gemini).get("/api/health").json()["extraction_cache"]


def test_health_says_the_cache_is_off_in_front_of_fake():
    # The setting is ignored for fake (get_provider never wraps it): say what happens.
    assert not client(extraction_cache=True).get("/api/health").json()["extraction_cache"]
