import asyncio
import logging
from datetime import date

import pymupdf
import pytest

from app.extraction.fake_provider import FIXTURES_DIR, FakeProvider
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.pipeline.ingest import SourcePage
from app.pipeline.service import (
    SAVE_FAILED,
    UNEXPECTED_ERROR,
    ExtractedPage,
    TooManyPages,
    UploadedFile,
    extract_files,
)
from app.schemas.extraction import RawExtraction

LIMITS = {"today": date(2026, 10, 19), "max_bytes": 20_000_000, "max_pages": 60}
# An upright page with real values (Meuhedet; national ID read as 0011223344).
UPRIGHT = RawExtraction.model_validate_json(
    (FIXTURES_DIR / "01_meuhedet_clean.json").read_text(encoding="utf-8")
)


def make_pdf(pages: int) -> bytes:
    with pymupdf.open() as doc:
        for _ in range(pages):
            doc.new_page(width=595, height=842)
        return doc.tobytes()


def upload(pages: int, filename: str = "forms.pdf") -> UploadedFile:
    return UploadedFile(filename=filename, data=make_pdf(pages))


class PageScript:
    """Answers each page by (filename, page_number): an exception to raise, or a delay.

    Records which pages were called and the most calls in flight at once.
    """

    def __init__(self, errors=None, delays=None) -> None:
        self.errors = errors or {}
        self.delays = delays or {}
        self.called: list[tuple[str, int]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def extract(self, page: PageImage) -> RawExtraction:
        key = (page.filename, page.page_number)
        self.called.append(key)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delays.get(key, 0))
            if key in self.errors:
                raise self.errors[key]
            return UPRIGHT.model_copy(deep=True)
        finally:
            self.in_flight -= 1


@pytest.fixture
def instant_render(monkeypatch):
    """For the timing tests: a real render takes ~0.1s one page at a time, which
    would make the order of events depend on the machine."""

    async def render_async(self, rotation=0):
        return PageImage(self.file_id, self.filename, self.page_number, rotation, b"jpeg")

    monkeypatch.setattr(SourcePage, "render_async", render_async)


def run(files, provider, max_concurrency=4, **overrides):
    limits = {**LIMITS, **overrides}
    return asyncio.run(extract_files(files, provider, max_concurrency=max_concurrency, **limits))


def test_every_page_of_every_file_comes_back_ruled():
    result = run([upload(2, "a.pdf"), upload(1, "b.pdf")], PageScript())

    assert [(f.filename, f.page_count, f.status) for f in result.files] == [
        ("a.pdf", 2, "ok"),
        ("b.pdf", 1, "ok"),
    ]
    assert [(p.form.source_file, p.form.page_number) for p in result.pages] == [
        ("a.pdf", 1),
        ("a.pdf", 2),
        ("b.pdf", 1),
    ]
    page = result.pages[0]
    national_id = page.form.fields.national_id
    assert (national_id.raw, national_id.value) == ("0011223344", "011223344")  # the rules ran
    assert page.form.form_id == f"{result.files[0].file_id}#p1"
    assert page.image.jpeg.startswith(b"\xff\xd8")  # the image for the preview
    assert (page.calls, result.failed_pages, result.quota_exhausted) == (1, [], False)


def test_each_file_gets_its_own_id():
    result = run([upload(1, "same.pdf"), upload(1, "same.pdf")], PageScript())

    assert len({f.file_id for f in result.files}) == 2


def test_an_invalid_file_is_reported_and_the_others_go_on():
    files = [UploadedFile("notes.docx", b"PK\x03\x04 a .docx"), upload(1, "ok.pdf")]

    result = run(files, PageScript())

    bad, good = result.files
    assert (bad.status, bad.page_count, bad.error.code) == ("error", 0, "INVALID_FILE")
    assert "לא נתמך" in bad.error.message
    assert good.status == "ok"
    assert [p.form.source_file for p in result.pages] == ["ok.pdf"]


def test_too_many_pages_across_files_fails_before_any_call():
    provider = PageScript()

    with pytest.raises(TooManyPages) as error:
        run([upload(2, "a.pdf"), upload(2, "b.pdf")], provider, max_pages=3)

    assert "4 עמודים" in error.value.message
    assert provider.called == []


def test_a_failed_page_does_not_stop_the_others():
    provider = PageScript(errors={("forms.pdf", 2): ProviderError("המודל לא ענה")})

    result = run([upload(3)], provider)

    assert [p.form.page_number for p in result.pages] == [1, 3]
    [failed] = result.failed_pages
    assert (failed.page_number, failed.source_file) == (2, "forms.pdf")
    assert (failed.error.code, failed.error.message) == ("EXTRACTION_FAILED", "המודל לא ענה")
    assert not result.quota_exhausted


def test_an_unexpected_error_fails_only_its_page_and_logs_no_content(caplog):
    secret = "ישראל ישראלי 0011223344"
    provider = PageScript(errors={("patient.pdf", 1): ValueError(secret)})

    with caplog.at_level(logging.INFO, logger="app.pipeline.service"):
        result = run([upload(2, "patient.pdf")], provider)

    [failed] = result.failed_pages
    assert failed.error.message == UNEXPECTED_ERROR
    assert [p.form.page_number for p in result.pages] == [2]
    assert "ValueError" in caplog.text
    assert secret not in caplog.text
    assert "patient.pdf" not in caplog.text  # a file name can be a patient's name


@pytest.mark.usefixtures("instant_render")
def test_a_used_up_quota_fails_the_pages_not_started_without_calling():
    provider = PageScript(errors={("forms.pdf", 2): QuotaExhausted("המכסה היומית נגמרה")})

    result = run([upload(4)], provider, max_concurrency=1)

    assert provider.called == [("forms.pdf", 1), ("forms.pdf", 2)]
    assert [p.form.page_number for p in result.pages] == [1]
    assert [p.page_number for p in result.failed_pages] == [2, 3, 4]
    assert {p.error.message for p in result.failed_pages} == {"המכסה היומית נגמרה"}
    assert result.quota_exhausted


@pytest.mark.usefixtures("instant_render")
def test_pages_in_flight_finish_when_the_quota_runs_out():
    # Page 1 is slow and already called when page 2 hits the quota: its reading is kept.
    provider = PageScript(
        errors={("forms.pdf", 2): QuotaExhausted("המכסה היומית נגמרה")},
        delays={("forms.pdf", 1): 0.05},
    )

    result = run([upload(3)], provider, max_concurrency=2)

    assert [p.form.page_number for p in result.pages] == [1]
    assert [p.page_number for p in result.failed_pages] == [2, 3]
    assert ("forms.pdf", 3) not in provider.called


@pytest.mark.usefixtures("instant_render")
def test_no_more_than_max_concurrency_calls_at_once():
    provider = PageScript(delays={("forms.pdf", n): 0.02 for n in range(1, 9)})

    result = run([upload(8)], provider, max_concurrency=3)

    assert len(result.pages) == 8
    assert provider.max_in_flight == 3


def test_zero_concurrency_is_refused_instead_of_hanging():
    with pytest.raises(ValueError):
        run([upload(1)], PageScript(), max_concurrency=0)


@pytest.mark.usefixtures("instant_render")
def test_pages_keep_upload_order_when_they_finish_out_of_order():
    provider = PageScript(delays={("forms.pdf", 1): 0.05, ("forms.pdf", 2): 0.0})

    result = run([upload(3)], provider)

    assert [p.form.page_number for p in result.pages] == [1, 2, 3]


@pytest.mark.usefixtures("instant_render")
def test_with_fake_provider_rotated_pages_are_straightened():
    # 7 fixtures + 1 error: an 8-page file meets each of them once.
    result = run([upload(8, "fixtures.pdf")], FakeProvider())

    assert len(result.pages) == 7
    assert len(result.failed_pages) == 1
    rotated = [p for p in result.pages if p.form.applied_rotation]
    assert {p.form.applied_rotation for p in rotated} == {90, 270}
    assert all(p.calls == 2 for p in rotated)
    assert all(isinstance(p, ExtractedPage) for p in result.pages)


# --- Saving each page as it finishes


class Saver:
    """Records the order of events and how many saves ran at once.

    Returns a string per page in place of real Records: the service only passes them on.
    """

    def __init__(self, fail_on=(), delay=0.0) -> None:
        self.fail_on = set(fail_on)
        self.delay = delay
        self.saved: list[int] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def __call__(self, page: ExtractedPage):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if page.form.page_number in self.fail_on:
                raise RuntimeError("ישראל ישראלי: connection lost")
            self.saved.append(page.form.page_number)
            return [f"record of p{page.form.page_number}"]
        finally:
            self.in_flight -= 1


@pytest.mark.usefixtures("instant_render")
def test_each_page_is_saved_once_with_its_records():
    provider = PageScript(errors={("forms.pdf", 2): ProviderError("המודל לא ענה")})
    saver = Saver()

    result = run([upload(3)], provider, save_page=saver)

    assert sorted(saver.saved) == [1, 3]  # a failed page is not saved (A7)
    assert [p.records for p in result.pages] == [["record of p1"], ["record of p3"]]


@pytest.mark.usefixtures("instant_render")
def test_a_page_is_saved_before_the_slow_ones_finish():
    provider = PageScript(delays={("forms.pdf", 2): 0.1})
    saver = Saver()
    events = []

    async def save(page):
        events.append((page.form.page_number, provider.in_flight))
        return await saver(page)

    run([upload(2)], provider, save_page=save)

    # Page 1 was saved while page 2 was still with the model, not at the end.
    assert events == [(1, 1), (2, 0)]


@pytest.mark.usefixtures("instant_render")
def test_saves_never_run_at_the_same_time():
    saver = Saver(delay=0.02)

    result = run([upload(6)], PageScript(), max_concurrency=4, save_page=saver)

    assert len(result.pages) == 6
    assert saver.max_in_flight == 1


@pytest.mark.usefixtures("instant_render")
def test_a_failed_save_fails_its_page_and_logs_no_content(caplog):
    saver = Saver(fail_on={2})

    with caplog.at_level(logging.INFO, logger="app.pipeline.service"):
        result = run([upload(3)], PageScript(), save_page=saver)

    assert [p.form.page_number for p in result.pages] == [1, 3]
    [failed] = result.failed_pages
    assert (failed.page_number, failed.error.message) == (2, SAVE_FAILED)
    assert "RuntimeError" in caplog.text
    assert "ישראל" not in caplog.text
