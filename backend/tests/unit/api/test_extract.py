import asyncio
import os
import tempfile

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.api import extract
from app.extraction.fake_provider import FIXTURES_DIR
from app.extraction.provider import PageImage, ProviderError
from app.main import create_app
from app.schemas.extraction import RawExtraction
from app.settings import Settings, get_settings

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


class Answers:
    """Every page reads as Maccabi, except the pages listed as errors."""

    def __init__(self, errors=()) -> None:
        self.errors = set(errors)

    async def extract(self, page: PageImage) -> RawExtraction:
        if page.page_number in self.errors:
            raise ProviderError("המודל לא ענה")
        return MACCABI.model_copy(deep=True)


@pytest.fixture
def make_client():
    def build(provider=None, save_page=None, **settings):
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings)
        app.dependency_overrides[extract.get_provider] = lambda: provider or Answers()
        if save_page:
            app.dependency_overrides[extract.get_save_page] = lambda: save_page
        return TestClient(app)

    return build


def upload(*files):
    return [("files", (name, data, "application/pdf")) for name, data in files]


def test_every_page_comes_back_as_records(make_client):
    response = make_client().post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(2)), ("b.pdf", make_pdf(1)))
    )

    assert response.status_code == 200
    body = response.json()
    assert [(f["filename"], f["page_count"], f["status"]) for f in body["files"]] == [
        ("a.pdf", 2, "ok"),
        ("b.pdf", 1, "ok"),
    ]
    assert [(r["source_file"], r["page_number"]) for r in body["records"]] == [
        ("a.pdf", 1),
        ("a.pdf", 2),
        ("b.pdf", 1),
    ]
    record = body["records"][0]
    assert record["status"] == "pending"
    assert record["fields"]["commitment_number"]["value"] == "50364186"
    assert [c["value"] for c in record["central_numbers"]] == ["937309", "937310", "937311"]
    assert body["failed_pages"] == []


def test_a_failed_page_is_listed_and_the_others_saved(make_client):
    response = make_client(provider=Answers(errors={2})).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(3)))
    )

    body = response.json()
    assert [r["page_number"] for r in body["records"]] == [1, 3]
    [failed] = body["failed_pages"]
    assert (failed["page_number"], failed["error"]["message"]) == (2, "המודל לא ענה")


def test_an_invalid_file_is_reported_with_status_200(make_client):
    files = [("files", ("notes.docx", b"PK\x03\x04 a .docx", "application/octet-stream"))]

    response = make_client().post("/api/v1/extract", files=files)

    assert response.status_code == 200
    [result] = response.json()["files"]
    assert (result["status"], result["error"]["code"]) == ("error", "INVALID_FILE")


def test_each_page_is_saved_through_save_page(make_client):
    saved = []

    async def save(page):
        saved.append(page.form.page_number)
        return []

    make_client(save_page=save).post("/api/v1/extract", files=upload(("a.pdf", make_pdf(2))))

    assert sorted(saved) == [1, 2]


def test_files_stay_in_memory(make_client, monkeypatch):
    # Starlette spools a file over 1MB to disk by default; a form must never get there.
    def no_disk(self):
        raise AssertionError("the upload was written to a temporary file")

    monkeypatch.setattr(tempfile.SpooledTemporaryFile, "rollover", no_disk)
    big = make_pdf(noise_px=1000)
    assert len(big) > 2_000_000

    response = make_client().post("/api/v1/extract", files=upload(("big.pdf", big)))

    assert response.status_code == 200
    assert response.json()["files"][0]["status"] == "ok"


# --- Requests that can't be used at all: application/problem+json


def assert_problem(response, status, type_):
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert (body["status"], body["type"]) == (status, type_)
    assert body["title"]  # in Hebrew, for the user
    return body


def test_no_files(make_client):
    response = make_client().post("/api/v1/extract", files={"other": ("x.txt", b"x")})

    assert_problem(response, 400, "no_files")


def test_not_multipart(make_client):
    response = make_client().post("/api/v1/extract", json={"files": []})

    assert_problem(response, 415, "unsupported_media_type")


def test_a_request_over_the_size_limit_is_refused(make_client):
    big = make_pdf(noise_px=1000)

    response = make_client(max_request_mb=1).post("/api/v1/extract", files=upload(("big.pdf", big)))

    assert "1MB" in assert_problem(response, 413, "request_too_large")["title"]


def test_too_many_pages_across_files(make_client):
    response = make_client(max_pages_per_request=2).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(2)), ("b.pdf", make_pdf(1)))
    )

    assert "3 עמודים" in assert_problem(response, 413, "too_many_pages")["title"]


def test_too_many_files(make_client):
    files = upload(*[(f"{n}.pdf", make_pdf(1)) for n in range(3)])

    response = make_client(max_files_per_request=2).post("/api/v1/extract", files=files)

    assert "2 קבצים" in assert_problem(response, 400, "invalid_upload")["detail"]


def test_the_stream_is_capped_even_without_content_length():
    async def chunks():
        for _ in range(5):
            yield b"x" * 10

    async def read_all(limit):
        return [chunk async for chunk in extract._capped(chunks(), limit)]

    assert len(asyncio.run(read_all(50))) == 5
    with pytest.raises(extract._RequestTooLarge):
        asyncio.run(read_all(49))


def test_records_without_saving_gives_one_record_per_commitment(make_client):
    # Two commitment numbers on one page: two records, each with all central numbers.
    reading = MACCABI.model_copy(deep=True)
    reading.commitment_numbers = [
        reading.commitment_numbers[0],
        reading.commitment_numbers[0].model_copy(update={"value": "50364187"}),
    ]

    class TwoCommitments:
        async def extract(self, page):
            return reading.model_copy(deep=True)

    response = make_client(provider=TwoCommitments()).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(1)))
    )

    records = response.json()["records"]
    assert [r["commitment_index"] for r in records] == [0, 1]
    assert len({r["record_id"] for r in records}) == 2
    assert len({r["page_id"] for r in records}) == 1
    assert all(len(r["central_numbers"]) == 3 for r in records)
