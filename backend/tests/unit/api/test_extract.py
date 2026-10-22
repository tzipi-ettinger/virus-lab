import secrets
import tempfile
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette import formparsers

from app.api import extract
from app.api.deps import require_user
from app.extraction.cached_provider import CachedProvider
from app.extraction.gemini_provider import GeminiProvider
from app.main import create_app
from app.pipeline.service import ExtractedForm
from app.rules.records import build_records
from app.schemas.api import Record, User
from app.settings import Settings, get_settings
from app.storage.service import _to_record
from tests.unit.api.uploads import QUOTA, Answers, make_pdf, upload

SIGNED_IN = User(id="u1", username="dana", display_name="דנה")


async def unsaved_records(extracted: ExtractedForm) -> list[Record]:
    """What form_saver returns, without a database or a user. Saving itself is
    tested in test_extract_saves.py."""
    form = extracted.form
    page_id = f"p_{secrets.token_hex(8)}"
    now = datetime.now(UTC)
    return [_to_record(draft, form, page_id, [], now) for draft in build_records(form)]


@pytest.fixture
def make_client():
    def build(provider=None, save_form=None, **settings):
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings)
        app.dependency_overrides[extract.get_provider] = lambda: provider or Answers()
        app.dependency_overrides[extract.get_save_form] = lambda: save_form or unsaved_records
        app.dependency_overrides[require_user] = lambda: SIGNED_IN
        return TestClient(app)

    return build


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
    assert body["quota_exhausted"] is False


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


def test_each_form_is_saved_through_save_form(make_client):
    saved = []

    async def save(extracted):
        saved.append(extracted.form.page_number)
        return []

    make_client(save_form=save).post("/api/v1/extract", files=upload(("a.pdf", make_pdf(2))))

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

    assert "2 קבצים" in assert_problem(response, 400, "too_many_files")["title"]


def test_thousands_of_empty_files_are_stopped_at_the_limit(make_client, monkeypatch):
    # 60MB can hold a million empty "files"; the parser must stop at the limit rather
    # than build an object for each (100k of them took 38s and 134MB).
    created = []
    original = formparsers.UploadFile.__init__

    def counting(self, *args, **kwargs):
        created.append(1)
        original(self, *args, **kwargs)

    monkeypatch.setattr(formparsers.UploadFile, "__init__", counting)
    body = multipart(*[("a.pdf", b"")] * 5_000)

    response = make_client().post("/api/v1/extract", content=body, headers=MULTIPART)

    assert_problem(response, 400, "too_many_files")
    assert len(created) <= 21  # MAX_FILES_PER_REQUEST is 20


def multipart(*parts: tuple[str, bytes], boundary: str = "XYZ", closed: bool = True) -> bytes:
    """A multipart body by hand, to send it chunked or cut it off."""
    body = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; filename="{name}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n".encode()
        + data
        + b"\r\n"
        for name, data in parts
    )
    return body + (f"--{boundary}--\r\n".encode() if closed else b"")


MULTIPART = {"content-type": "multipart/form-data; boundary=XYZ"}


def test_a_chunked_request_with_no_content_length_is_still_capped(make_client):
    # The test client sends Content-Length for a normal upload; a generator body is
    # sent chunked, without one, so only the cap while reading can stop it.
    body = multipart(("big.pdf", make_pdf(noise_px=1000)))

    def chunks():
        for start in range(0, len(body), 64_000):
            yield body[start : start + 64_000]

    response = make_client(max_request_mb=1).post(
        "/api/v1/extract", content=chunks(), headers=MULTIPART
    )

    assert "content-length" not in response.request.headers
    assert_problem(response, 413, "request_too_large")


def test_a_chunked_request_under_the_limit_goes_through(make_client):
    body = multipart(("a.pdf", make_pdf(1)))

    response = make_client().post("/api/v1/extract", content=iter([body]), headers=MULTIPART)

    assert response.status_code == 200
    assert [f["status"] for f in response.json()["files"]] == ["ok"]


def test_an_upload_cut_off_in_the_middle_is_invalid_not_empty(make_client):
    # Starlette parses it without an error and drops the unfinished file, which
    # looked like "no files chosen".
    whole = multipart(("a.pdf", make_pdf(1)), ("b.pdf", make_pdf(1)))
    cut = whole[: len(whole) - 300]

    response = make_client().post("/api/v1/extract", content=cut, headers=MULTIPART)

    body = assert_problem(response, 400, "invalid_upload")
    assert "נקטעה" in body["title"]


def test_a_hebrew_file_name_comes_back_as_sent(make_client):
    name = "התחייבויות - חלק 1.pdf"

    response = make_client().post("/api/v1/extract", files=upload((name, make_pdf(1))))

    assert response.json()["files"][0]["filename"] == name
    assert response.json()["records"][0]["source_file"] == name


def test_an_empty_file_input_counts_as_no_files(make_client):
    # What a browser sends when the form is submitted with no file chosen.
    files = [("files", ("", b"", "application/octet-stream"))]

    response = make_client().post("/api/v1/extract", files=files)

    assert_problem(response, 400, "no_files")


# --- The daily quota runs out: is sending the file again safe?


def test_quota_after_a_page_was_saved_is_200_with_the_saved_records(make_client):
    response = make_client(provider=Answers(quota_from=2), max_concurrency=1).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(3)))
    )

    assert response.status_code == 200
    body = response.json()
    assert body["quota_exhausted"] is True
    assert [r["page_number"] for r in body["records"]] == [1]
    assert [(p["page_number"], p["error"]["code"]) for p in body["failed_pages"]] == [
        (2, "QUOTA_EXHAUSTED"),
        (3, "QUOTA_EXHAUSTED"),
    ]


def test_quota_before_anything_was_saved_is_503(make_client):
    response = make_client(provider=Answers(quota_from=1)).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(2)))
    )

    body = assert_problem(response, 503, "quota_exhausted")
    assert body["title"] == QUOTA  # the provider's Hebrew message


def test_quota_after_a_page_failed_for_another_reason_is_still_503(make_client):
    # Page 1 failed and page 2 hit the quota: nothing was saved, so sending again is safe.
    response = make_client(provider=Answers(errors={1}, quota_from=2), max_concurrency=1).post(
        "/api/v1/extract", files=upload(("a.pdf", make_pdf(3)))
    )

    assert_problem(response, 503, "quota_exhausted")


def test_gemini_is_one_provider_for_every_request():
    # Its semaphore limits the whole server only if every request gets the same one.
    settings = Settings(
        _env_file=None, extraction_provider="gemini", gemini_api_keys="k1,k2", gemini_model="m"
    )

    first, second = extract.get_provider(settings), extract.get_provider(settings)

    assert isinstance(first, GeminiProvider)
    assert first is second


def test_the_cache_sits_in_front_of_gemini_only_when_turned_on():
    on = Settings(
        _env_file=None,
        extraction_provider="gemini",
        gemini_api_key="k",
        gemini_model="m",
        extraction_cache=True,
    )
    off = on.model_copy(update={"extraction_cache": False})

    cached = extract.get_provider(on)

    assert isinstance(cached, CachedProvider)
    assert extract.get_provider(on) is cached  # one cache, so its counts add up
    assert isinstance(extract.get_provider(off), GeminiProvider)


def test_the_cache_is_off_by_default_and_never_wraps_fake():
    assert Settings(_env_file=None).extraction_cache is False
    fake = extract.get_provider(Settings(_env_file=None, extraction_cache=True))
    assert not isinstance(fake, CachedProvider)
