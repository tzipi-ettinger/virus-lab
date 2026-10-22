import asyncio
from contextlib import asynccontextmanager

import psycopg
from fastapi.testclient import TestClient

from app.api import health
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
        "database": "off",
        "extraction_provider": "fake",
        "extraction_cache": False,
        "gemini_keys": 0,
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


# --- The database (Render's health check calls this path)


class FailingPool:
    """A pool whose database refuses or never answers."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    @asynccontextmanager
    async def connection(self):
        if self.error is not None:
            raise self.error
        await asyncio.sleep(60)  # hangs, like a database behind a dead network
        yield


def client_with_pool(pool) -> TestClient:
    app = create_app(Settings(_env_file=None))
    app.state.pool = pool  # no lifespan: TestClient without `with` doesn't run it
    return TestClient(app)


def test_health_says_the_database_is_off_without_database_url():
    # Locally and in CI's image check: still healthy, so the image check passes.
    response = client().get("/api/health")

    assert response.status_code == 200
    assert response.json()["database"] == "off"


def test_health_checks_a_real_database(db):
    settings = Settings(_env_file=None, database_url=db.url)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    # with: the lifespan opens the pool. A selector loop: psycopg async can't use Proactor.
    with TestClient(app, backend_options={"loop_factory": asyncio.SelectorEventLoop}) as live:
        response = live.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"


def test_health_is_503_when_the_database_refuses():
    response = client_with_pool(FailingPool(psycopg.OperationalError("password=secret"))).get(
        "/api/health"
    )

    assert response.status_code == 503
    assert response.json()["status"] == "error"
    assert response.json()["database"] == "unavailable"
    assert "secret" not in response.text


def test_health_is_503_when_the_database_does_not_answer_in_time(monkeypatch):
    monkeypatch.setattr(health, "DB_CHECK_TIMEOUT_S", 0.05)

    response = client_with_pool(FailingPool()).get("/api/health")

    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_health_logs_the_error_type_but_not_its_text(caplog):
    client_with_pool(FailingPool(psycopg.OperationalError("password=secret"))).get("/api/health")

    assert "OperationalError" in caplog.text
    assert "secret" not in caplog.text
