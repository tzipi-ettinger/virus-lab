"""POST /api/v1/extract answers 202 at once, and GET /api/v1/extract/jobs/{job_id}
follows the job. What the job reads and saves is tested in test_extract.py."""

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.api import extract
from app.api.deps import require_user
from app.main import create_app
from app.pipeline.jobs import BUSY_FOR_USER, ExtractJobs
from app.schemas.api import User
from app.settings import Settings, get_settings
from tests.unit.api.test_extract import SIGNED_IN, unsaved_records
from tests.unit.api.uploads import Answers, finish, make_pdf, upload

OTHER = User(id="u2", username="noa", display_name="נועה")


class Gated(Answers):
    """Answers like Answers, each page only once the test lets it."""

    def __init__(self) -> None:
        super().__init__()
        self.gate = threading.Semaphore(0)

    async def extract(self, page):
        assert await asyncio.to_thread(self.gate.acquire, timeout=10), "never let through"
        return await super().extract(page)


@pytest.fixture
def signed_in():
    return {"user": SIGNED_IN}


@pytest.fixture
def provider():
    return Gated()


@pytest.fixture
def client(provider, signed_in):
    settings = Settings(_env_file=None, max_concurrency=1)
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[extract.get_provider] = lambda: provider
    app.dependency_overrides[extract.get_save_form] = lambda: unsaved_records
    app.dependency_overrides[require_user] = lambda: signed_in["user"]
    with TestClient(app) as client:
        yield client
        for _ in range(100):  # let any job still waiting end, so the loop can close
            provider.gate.release()


def job_of(client, job_id):
    return client.get(f"/api/v1/extract/jobs/{job_id}")


def wait_until(client, job_id, condition, timeout_s=5):
    deadline = time.monotonic() + timeout_s
    while not condition(job := job_of(client, job_id).json()):
        assert time.monotonic() < deadline, f"not reached: {job}"
        time.sleep(0.01)
    return job


def test_the_upload_is_answered_before_any_page_is_read(client, provider):
    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(3))))

    assert response.status_code == 202
    started = response.json()
    assert (started["status"], started["result"], started["problem"]) == ("running", None, None)

    job = wait_until(client, started["job_id"], lambda job: job["total"] == 3)
    assert (job["status"], job["done"]) == ("running", 0)

    provider.gate.release()
    job = wait_until(client, started["job_id"], lambda job: job["done"] == 1)
    assert job["status"] == "running"

    provider.gate.release()
    provider.gate.release()
    done = finish(client, response)
    assert (done["status"], done["done"], done["total"]) == ("done", 3, 3)
    assert len(done["result"]["records"]) == 3


def test_the_job_is_not_cached_by_the_browser(client):
    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))

    polled = job_of(client, response.json()["job_id"])

    assert polled.status_code == 200
    assert polled.headers["cache-control"] == "no-store"


def test_an_unknown_job_is_404(client):
    response = job_of(client, "no-such-job")

    assert response.status_code == 404
    assert response.json()["type"] == "job_not_found"


def test_another_user_sees_the_job_too(client, signed_in):
    # As on the records screen: everyone sees everyone's uploads.
    response = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))

    signed_in["user"] = OTHER
    polled = job_of(client, response.json()["job_id"])

    assert polled.status_code == 200
    assert polled.json()["job_id"] == response.json()["job_id"]


def test_too_many_uploads_at_once_are_refused_before_reading(client):
    client.app.state.jobs = ExtractJobs(max_running_per_user=1)
    client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))

    response = client.post("/api/v1/extract", files=upload(("b.pdf", make_pdf(1))))

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"] == "too_many_uploads"
    assert response.json()["title"] == BUSY_FOR_USER


def test_a_refused_request_starts_no_job(client):
    client.app.state.jobs = jobs = ExtractJobs(max_running_per_user=1)

    refused = client.post("/api/v1/extract", content=b"not multipart")
    accepted = client.post("/api/v1/extract", files=upload(("a.pdf", make_pdf(1))))

    assert refused.status_code == 415
    assert accepted.status_code == 202  # the refused one took no place
    assert jobs.get(accepted.json()["job_id"]) is not None
