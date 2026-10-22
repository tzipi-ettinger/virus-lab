"""Uploads for the /extract tests: generated PDFs and a provider that answers
from a fixture. No sample data."""

import os
import time

import pymupdf

from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.schemas.extraction import RawExtraction

# Maccabi, one page with three central numbers and one commitment number.
MACCABI = RawExtraction.model_validate_json(
    (FIXTURES_DIR / "03_maccabi_three_centrals.json").read_text(encoding="utf-8")
)


def make_pdf(pages: int = 1, noise_px: int = 0) -> bytes:
    """A blank PDF; noise_px adds a random (incompressible) image to make it big."""
    with pymupdf.open() as doc:
        for _ in range(pages):
            page = doc.new_page(width=595, height=842)
            if noise_px:
                samples = os.urandom(noise_px * noise_px * 3)
                image = pymupdf.Pixmap(pymupdf.csRGB, noise_px, noise_px, samples, False)
                page.insert_image(page.rect, stream=image.tobytes("png"))
        return doc.tobytes()


QUOTA = "המכסה היומית של Gemini נגמרה. אפשר לנסות שוב מחר"


class Answers:
    """Every page reads as Maccabi, except the listed pages: an error, or the quota."""

    def __init__(self, errors=(), quota_from=None) -> None:
        self.errors = set(errors)
        self.quota_from = quota_from

    async def extract(self, page: PageImage) -> RawExtraction:
        if self.quota_from is not None and page.page_number >= self.quota_from:
            raise QuotaExhausted(QUOTA)
        if page.page_number in self.errors:
            raise ProviderError("המודל לא ענה")
        return MACCABI.model_copy(deep=True)


def upload(*files):
    return [("files", (name, data, "application/pdf")) for name, data in files]


def finish(client, response, timeout_s: float = 10) -> dict:
    """The job a 202 from POST /extract started, once it is over (polls like the page).

    The client must be used as a context manager (`with TestClient(app)`): otherwise
    each request gets its own event loop, and the job dies with the first one."""
    assert response.status_code == 202, response.text
    job = response.json()
    deadline = time.monotonic() + timeout_s
    while job["status"] == "running":
        assert time.monotonic() < deadline, f"the job is still running: {job}"
        time.sleep(0.01)
        polled = client.get(f"/api/v1/extract/jobs/{job['job_id']}")
        assert polled.status_code == 200, polled.text
        job = polled.json()
    return job
