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
    assert response.json() == {"status": "ok", "extraction_provider": "fake"}


def test_health_shows_when_the_server_reads_with_gemini():
    response = client(extraction_provider="gemini", gemini_api_key="k", gemini_model="m").get(
        "/api/health"
    )

    assert response.json()["extraction_provider"] == "gemini"
    assert "k" not in response.json().values()  # never the key
