import asyncio
import logging
from datetime import date

import pymupdf
import pytest

from app.extraction.fake_provider import FIXTURES_DIR, FakeProvider
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.pipeline import service
from app.pipeline.ingest import SAVE_MAX_SIDE_PX, SourcePage
from app.pipeline.service import (
    SAVE_FAILED,
    UNEXPECTED_ERROR,
    ExtractedForm,
    TooManyPages,
    UploadedFile,
    extract_files,
)
from app.schemas.extraction import NamePart, NameReading, RawExtraction, RawField, RawFormBox

LIMITS = {"today": date(2026, 10, 19), "max_bytes": 20_000_000, "max_pages": 60}
# An upright page with real values (Meuhedet; national ID read as 0011223344).
UPRIGHT = RawExtraction.model_validate_json(
    (FIXTURES_DIR / "01_meuhedet_clean.json").read_text(encoding="utf-8")
)
_NOTHING = RawField(value=None, status="not_found", evidence=None)
# A page with nothing on it that names a form or a patient: a continuation page.
BLANK = UPRIGHT.model_copy(
    update={
        **{name: _NOTHING for name in ("first_name", "last_name", "national_id")},
        "central_numbers": [],
        "commitment_numbers": [],
    }
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

    def __init__(self, errors=None, delays=None, readings=None) -> None:
        self.errors = errors or {}
        self.delays = delays or {}
        self.readings = readings or {}  # pages that read as something other than UPRIGHT
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
            return self.readings.get(key, UPRIGHT).model_copy(deep=True)
        finally:
            self.in_flight -= 1


@pytest.fixture
def instant_render(monkeypatch):
    """For the timing tests: a real render takes ~0.1s one page at a time, which
    would make the order of events depend on the machine."""

    async def render_async(self, rotation=0, **size):
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
    assert [(p.form.source_file, p.form.page_number) for p in result.forms] == [
        ("a.pdf", 1),
        ("a.pdf", 2),
        ("b.pdf", 1),
    ]
    page = result.forms[0]
    national_id = page.form.fields.national_id
    assert (national_id.raw, national_id.value) == ("0011223344", "011223344")  # the rules ran
    assert page.form.form_id == f"{result.files[0].file_id}-p1"
    saved = page.images[0]
    assert saved.jpeg.startswith(b"\xff\xd8")  # the image for the preview
    assert max(pymupdf.Pixmap(saved.jpeg).width, pymupdf.Pixmap(saved.jpeg).height) == (
        pytest.approx(SAVE_MAX_SIDE_PX, abs=2)  # the saved size, not the model's
    )
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
    assert [p.form.source_file for p in result.forms] == ["ok.pdf"]


def test_an_unexpected_error_on_one_file_fails_only_that_file(monkeypatch):
    split = service.split_pages_async

    async def split_or_crash(file_id, filename, data, **limits):
        if filename == "crash.pdf":
            raise KeyError("ישראל ישראלי")
        return await split(file_id, filename, data, **limits)

    monkeypatch.setattr(service, "split_pages_async", split_or_crash)

    result = run([upload(1, "crash.pdf"), upload(1, "ok.pdf")], PageScript())

    crashed, good = result.files
    assert (crashed.status, crashed.error.code) == ("error", "EXTRACTION_FAILED")
    assert crashed.error.message == UNEXPECTED_ERROR
    assert good.status == "ok"
    assert [p.form.source_file for p in result.forms] == ["ok.pdf"]


def test_too_many_pages_across_files_fails_before_any_call():
    provider = PageScript()

    with pytest.raises(TooManyPages) as error:
        run([upload(2, "a.pdf"), upload(2, "b.pdf")], provider, max_pages=3)

    assert "4 עמודים" in error.value.message
    assert provider.called == []


def test_a_failed_page_does_not_stop_the_others():
    provider = PageScript(errors={("forms.pdf", 2): ProviderError("המודל לא ענה")})

    result = run([upload(3)], provider)

    assert [p.form.page_number for p in result.forms] == [1, 3]
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
    assert [p.form.page_number for p in result.forms] == [2]
    assert "ValueError" in caplog.text
    assert secret not in caplog.text
    assert "patient.pdf" not in caplog.text  # a file name can be a patient's name


@pytest.mark.usefixtures("instant_render")
def test_a_used_up_quota_fails_the_pages_not_started_without_calling():
    provider = PageScript(errors={("forms.pdf", 2): QuotaExhausted("המכסה היומית נגמרה")})

    result = run([upload(4)], provider, max_concurrency=1)

    assert provider.called == [("forms.pdf", 1), ("forms.pdf", 2)]
    assert [p.form.page_number for p in result.forms] == [1]
    assert [p.page_number for p in result.failed_pages] == [2, 3, 4]
    assert {p.error.message for p in result.failed_pages} == {"המכסה היומית נגמרה"}
    # Read or not even sent, they all failed on the quota, not on the model.
    assert {p.error.code for p in result.failed_pages} == {"QUOTA_EXHAUSTED"}
    assert result.quota_exhausted
    assert result.quota_message == "המכסה היומית נגמרה"


@pytest.mark.usefixtures("instant_render")
def test_an_ordinary_failure_stays_extraction_failed_next_to_a_used_up_quota():
    provider = PageScript(
        errors={
            ("forms.pdf", 1): ProviderError("המודל לא ענה"),
            ("forms.pdf", 2): QuotaExhausted("המכסה היומית נגמרה"),
        }
    )

    result = run([upload(3)], provider, max_concurrency=1)

    assert [(p.page_number, p.error.code) for p in result.failed_pages] == [
        (1, "EXTRACTION_FAILED"),
        (2, "QUOTA_EXHAUSTED"),
        (3, "QUOTA_EXHAUSTED"),
    ]


@pytest.mark.usefixtures("instant_render")
def test_pages_in_flight_finish_when_the_quota_runs_out():
    # Page 1 is slow and already called when page 2 hits the quota: its reading is kept.
    provider = PageScript(
        errors={("forms.pdf", 2): QuotaExhausted("המכסה היומית נגמרה")},
        delays={("forms.pdf", 1): 0.05},
    )

    result = run([upload(3)], provider, max_concurrency=2)

    assert [p.form.page_number for p in result.forms] == [1]
    assert [p.page_number for p in result.failed_pages] == [2, 3]
    assert ("forms.pdf", 3) not in provider.called


@pytest.mark.usefixtures("instant_render")
def test_no_more_than_max_concurrency_calls_at_once():
    provider = PageScript(delays={("forms.pdf", n): 0.02 for n in range(1, 9)})

    result = run([upload(8)], provider, max_concurrency=3)

    assert len(result.forms) == 8
    assert provider.max_in_flight == 3


def test_zero_concurrency_is_refused_instead_of_hanging():
    with pytest.raises(ValueError):
        run([upload(1)], PageScript(), max_concurrency=0)


@pytest.mark.usefixtures("instant_render")
def test_pages_keep_upload_order_when_they_finish_out_of_order():
    provider = PageScript(delays={("forms.pdf", 1): 0.05, ("forms.pdf", 2): 0.0})

    result = run([upload(3)], provider)

    assert [p.form.page_number for p in result.forms] == [1, 2, 3]


@pytest.mark.usefixtures("instant_render")
def test_with_fake_provider_rotated_pages_are_straightened():
    # 7 fixtures + 1 error: an 8-page file meets each of them once.
    result = run([upload(8, "fixtures.pdf")], FakeProvider())

    assert len(result.forms) == 7
    assert len(result.failed_pages) == 1
    rotated = [p for p in result.forms if p.form.applied_rotation]
    assert {p.form.applied_rotation for p in rotated} == {90, 270}
    assert all(p.calls == 2 for p in rotated)
    assert all(isinstance(p, ExtractedForm) for p in result.forms)


# --- Saving each form


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

    async def __call__(self, extracted: ExtractedForm):
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            if extracted.form.page_number in self.fail_on:
                raise RuntimeError("ישראל ישראלי: connection lost")
            self.saved.append(extracted.form.page_number)
            return [f"record of p{extracted.form.page_number}"]
        finally:
            self.in_flight -= 1


@pytest.mark.usefixtures("instant_render")
def test_each_page_is_saved_once_with_its_records():
    provider = PageScript(errors={("forms.pdf", 2): ProviderError("המודל לא ענה")})
    saver = Saver()

    result = run([upload(3)], provider, save_form=saver)

    assert sorted(saver.saved) == [1, 3]  # a failed page is not saved (A7)
    assert [p.records for p in result.forms] == [["record of p1"], ["record of p3"]]


@pytest.mark.usefixtures("instant_render")
def test_a_form_is_saved_once_the_next_page_is_read_not_at_the_end():
    provider = PageScript(delays={("forms.pdf", 3): 0.1})
    saver = Saver()
    events = []

    async def save(extracted):
        events.append((extracted.form.page_number, provider.in_flight))
        return await saver(extracted)

    run([upload(3)], provider, save_form=save)

    # Page 2 decided that page 1 is a form of its own, so page 1 was saved while
    # page 3 was still with the model. Page 2 waited for page 3.
    assert events == [(1, 1), (2, 0), (3, 0)]


@pytest.mark.usefixtures("instant_render")
def test_saves_never_run_at_the_same_time():
    saver = Saver(delay=0.02)

    result = run([upload(6)], PageScript(), max_concurrency=4, save_form=saver)

    assert len(result.forms) == 6
    assert saver.max_in_flight == 1


@pytest.mark.usefixtures("instant_render")
def test_a_failed_save_fails_its_page_and_logs_no_content(caplog):
    saver = Saver(fail_on={2})

    with caplog.at_level(logging.INFO, logger="app.pipeline.service"):
        result = run([upload(3)], PageScript(), save_form=saver)

    assert [p.form.page_number for p in result.forms] == [1, 3]
    [failed] = result.failed_pages
    assert (failed.page_number, failed.error.message) == (2, SAVE_FAILED)
    assert "RuntimeError" in caplog.text
    assert "ישראל" not in caplog.text


# --- Continuation pages (A1 in #15)


def test_a_page_without_a_central_number_joins_the_form_before_it():
    provider = PageScript(readings={("forms.pdf", 2): BLANK})
    saver = Saver()

    result = run([upload(3)], provider, save_form=saver)

    first, third = result.forms
    assert (first.form.page_number, first.form.continuation_pages) == (1, [2])
    assert [image.page_number for image in first.images] == [1, 2]
    assert (first.calls, first.form.issues) == (2, [])
    assert (third.form.page_number, third.form.continuation_pages) == (3, [])
    assert saver.saved == [1, 3]  # one save per form, not per page
    assert result.failed_pages == []


def test_a_form_never_continues_into_the_next_file():
    provider = PageScript(readings={("b.pdf", 1): BLANK})

    result = run([upload(1, "a.pdf"), upload(1, "b.pdf")], provider)

    assert [(f.form.source_file, f.form.continuation_pages) for f in result.forms] == [
        ("a.pdf", []),
        ("b.pdf", []),
    ]
    assert result.forms[1].form.issues == []  # a file's first page: nothing to doubt


def test_a_page_after_a_failed_page_is_its_own_form_flagged():
    provider = PageScript(
        errors={("forms.pdf", 2): ProviderError("המודל לא ענה")},
        readings={("forms.pdf", 3): BLANK},
    )

    result = run([upload(3)], provider)

    assert [f.form.page_number for f in result.forms] == [1, 3]
    assert [i.code for i in result.forms[1].form.issues] == ["PAGE_GROUPING_UNCERTAIN"]
    assert result.forms[1].form.needs_review
    assert [p.page_number for p in result.failed_pages] == [2]


def test_another_patient_on_a_page_without_a_central_number_is_flagged_not_attached():
    other = BLANK.model_copy(
        update={"national_id": RawField(value="000000018", status="found", evidence="ת.ז.")}
    )
    provider = PageScript(readings={("forms.pdf", 2): other})

    result = run([upload(2)], provider)

    assert [(f.form.page_number, f.form.continuation_pages) for f in result.forms] == [
        (1, []),
        (2, []),
    ]
    assert [i.code for i in result.forms[1].form.issues] == ["PAGE_GROUPING_UNCERTAIN"]


@pytest.mark.usefixtures("instant_render")
def test_a_failed_save_fails_every_page_of_its_form():
    # One transaction per form on B's side: none of its pages was saved.
    provider = PageScript(readings={("forms.pdf", 2): BLANK})

    result = run([upload(3)], provider, save_form=Saver(fail_on={1}))

    assert [f.form.page_number for f in result.forms] == [3]
    assert [(p.page_number, p.error.message) for p in result.failed_pages] == [
        (1, SAVE_FAILED),
        (2, SAVE_FAILED),
    ]


def test_a_join_that_fails_keeps_the_page_as_its_own_form_flagged(monkeypatch, caplog):
    def broken_join(group, page, *, today):
        raise KeyError("ישראל ישראלי")

    monkeypatch.setattr(service, "join", broken_join)
    provider = PageScript(readings={("forms.pdf", 2): BLANK})
    saver = Saver()

    with caplog.at_level(logging.INFO, logger="app.pipeline.service"):
        result = run([upload(3)], provider, save_form=saver)

    assert [f.form.page_number for f in result.forms] == [1, 2, 3]
    assert [i.code for i in result.forms[1].form.issues] == ["PAGE_GROUPING_UNCERTAIN"]
    assert saver.saved == [1, 2, 3]  # the upload went on
    assert "KeyError" in caplog.text
    assert "ישראל" not in caplog.text


def test_progress_counts_every_page_read_or_failed():
    seen = []
    provider = PageScript(errors={("a.pdf", 2): ProviderError("המודל לא ענה")})

    asyncio.run(
        extract_files(
            [upload(3, "a.pdf"), upload(1, "b.pdf")],
            provider,
            max_concurrency=1,
            on_progress=lambda done, total: seen.append((done, total)),
            **LIMITS,
        )
    )

    assert seen == [(0, 4), (1, 4), (2, 4), (3, 4), (4, 4)]


def test_progress_counts_pages_failed_for_the_quota_without_a_call():
    seen = []
    provider = PageScript(errors={("forms.pdf", 1): QuotaExhausted("נגמרה")})

    asyncio.run(
        extract_files(
            [upload(3)],
            provider,
            max_concurrency=1,
            on_progress=lambda done, total: seen.append((done, total)),
            **LIMITS,
        )
    )

    assert seen[-1] == (3, 3)
    assert provider.called == [("forms.pdf", 1)]


def test_no_progress_for_an_upload_over_the_page_limit():
    seen = []

    with pytest.raises(TooManyPages):
        asyncio.run(
            extract_files(
                [upload(2, "a.pdf"), upload(2, "b.pdf")],
                PageScript(),
                max_concurrency=1,
                on_progress=lambda done, total: seen.append((done, total)),
                **{**LIMITS, "max_pages": 3},
            )
        )

    assert seen == []


# --- Several forms on one page (split.py)

TWO_FORMS = [RawFormBox(box_2d=[0, 0, 480, 1000]), RawFormBox(box_2d=[520, 0, 1000, 1000])]


def patient(national_id: str, commitment: str) -> RawExtraction:
    return UPRIGHT.model_copy(
        update={
            "national_id": RawField(value=national_id, status="found", evidence="ת.ז."),
            "commitment_numbers": [RawField(value=commitment, status="found", evidence="התחייבות")],
        },
        deep=True,
    )


class SplitScript:
    """Pages in `split` report two forms; a cut form ("-f1", "-f2") reads as `parts[n]`.

    `errors` maps a part number to the exception it raises. Records every call.
    """

    def __init__(self, split=(), parts=None, errors=None) -> None:
        self.split = set(split)
        self.parts = parts or {}
        self.errors = errors or {}
        self.called: list[tuple[str, int, int]] = []  # (filename, page, part); part 0 = whole

    async def extract(self, page: PageImage) -> RawExtraction:
        _, _, suffix = page.file_id.partition("-f")
        part = int(suffix or 0)
        self.called.append((page.filename, page.page_number, part))
        if part in self.errors:
            raise self.errors[part]
        if part:
            return self.parts.get(part, UPRIGHT).model_copy(deep=True)
        if (page.filename, page.page_number) in self.split:
            return UPRIGHT.model_copy(update={"forms_on_page": TWO_FORMS}, deep=True)
        return UPRIGHT.model_copy(deep=True)


PARTS = {1: patient("000000018", "111111"), 2: patient("000000026", "222222")}


def test_a_page_with_two_forms_gives_two_forms_each_read_on_its_own():
    provider = SplitScript(split={("forms.pdf", 1)}, parts=PARTS)
    saver = Saver()

    result = run([upload(2)], provider, save_form=saver)

    file_id = result.files[0].file_id
    assert [(f.form.file_id, f.form.page_number) for f in result.forms] == [
        (f"{file_id}-f1", 1),
        (f"{file_id}-f2", 1),
        (file_id, 2),
    ]
    first, second, _ = result.forms
    assert first.form.fields.national_id.value == "000000018"
    assert second.form.fields.national_id.value == "000000026"
    assert [c.value for c in second.form.commitment_numbers] == ["222222"]
    assert [i.code for f in result.forms for i in f.form.issues] == []
    # Each form keeps its own cut-out image, and saves on its own.
    assert [image.file_id for image in second.images] == [f"{file_id}-f2"]
    assert saver.saved == [1, 1, 2]
    # The call that found the forms is counted once, with the first form.
    assert [f.calls for f in result.forms] == [2, 1, 1]
    # Page 2 runs alongside, so only the set of calls is fixed: no page turned.
    assert sorted(provider.called) == [
        ("forms.pdf", 1, 0),
        ("forms.pdf", 1, 1),
        ("forms.pdf", 1, 2),
        ("forms.pdf", 2, 0),
    ]
    assert result.failed_pages == []


def test_a_page_without_a_central_number_after_a_split_page_is_flagged():
    # It may continue either form: never attached to one of them.
    class Script(SplitScript):
        async def extract(self, page):
            if page.page_number == 2:
                return BLANK.model_copy(deep=True)
            return await super().extract(page)

    result = run([upload(2)], Script(split={("forms.pdf", 1)}, parts=PARTS))

    assert [(f.form.page_number, f.form.continuation_pages) for f in result.forms] == [
        (1, []),
        (1, []),
        (2, []),
    ]
    assert [i.code for i in result.forms[2].form.issues] == ["PAGE_GROUPING_UNCERTAIN"]


def test_a_cut_form_that_fails_fails_alone():
    provider = SplitScript(
        split={("forms.pdf", 1)}, parts=PARTS, errors={2: ProviderError("המודל לא ענה")}
    )

    result = run([upload(1)], provider)

    file_id = result.files[0].file_id
    assert [f.form.file_id for f in result.forms] == [f"{file_id}-f1"]
    [failed] = result.failed_pages
    assert (failed.file_id, failed.page_number, failed.error.message) == (
        f"{file_id}-f2",
        1,
        "המודל לא ענה",
    )


def test_the_quota_running_out_on_a_cut_form_fails_the_next_without_a_call():
    provider = SplitScript(split={("forms.pdf", 1)}, errors={1: QuotaExhausted("נגמרה המכסה")})

    result = run([upload(1)], provider)

    assert result.forms == []
    assert [p.error.code for p in result.failed_pages] == ["QUOTA_EXHAUSTED", "QUOTA_EXHAUSTED"]
    assert ("forms.pdf", 1, 2) not in provider.called
    assert result.quota_exhausted


def test_a_split_page_counts_once_in_the_progress():
    seen = []

    asyncio.run(
        extract_files(
            [upload(2)],
            SplitScript(split={("forms.pdf", 1)}),
            max_concurrency=2,
            on_progress=lambda done, total: seen.append((done, total)),
            **LIMITS,
        )
    )

    assert seen[0] == (0, 2)
    assert seen[-1] == (2, 2)


# --- The name's second read (names.py)

NAME_UNCLEAR = RawField(value=None, status="unclear", evidence="שם", box_2d=[300, 500, 320, 600])
READ_UP_CLOSE = NameReading(
    first_name=NamePart(value="ישראל", status="found", evidence="שם פרטי"),
    last_name=NamePart(value="ישראלי", status="found", evidence="שם משפחה"),
)


class NameScript(PageScript):
    """Reads crops too, the way Gemini does: every name comes back sure, up close."""

    def __init__(self) -> None:
        super().__init__()
        self.crops: list[PageImage] = []

    async def read_name(self, crop: PageImage) -> NameReading:
        self.crops.append(crop)
        return READ_UP_CLOSE.model_copy(deep=True)


def test_a_name_unclear_on_the_page_is_read_again_from_a_crop():
    provider = NameScript()
    provider.readings[("forms.pdf", 1)] = UPRIGHT.model_copy(
        update={"first_name": NAME_UNCLEAR, "last_name": NAME_UNCLEAR}
    )

    result = run([upload(1)], provider)

    [page] = result.forms
    first, last = page.form.fields.first_name, page.form.fields.last_name
    assert (first.raw, first.model_status, last.raw, last.model_status) == (
        "ישראל",
        "found",
        "ישראלי",
        "found",
    )
    assert page.calls == 2  # the page, then the crop
    assert len(provider.crops) == 1


def test_a_page_with_no_name_on_it_costs_no_second_call():
    provider = NameScript()  # UPRIGHT: its names are unclear, with no box to cut out

    result = run([upload(1)], provider)

    assert provider.crops == []
    assert result.forms[0].calls == 1


def test_a_split_page_has_its_names_read_again_form_by_form():
    # Page 2: a cut form is a one-page PDF that keeps its page number, so the crop
    # must draw its PDF's only page, not page 2.
    class Script(SplitScript):
        def __init__(self) -> None:
            names = {"first_name": NAME_UNCLEAR, "last_name": NAME_UNCLEAR}
            parts = {n: reading.model_copy(update=names) for n, reading in PARTS.items()}
            super().__init__(split={("forms.pdf", 2)}, parts=parts)
            self.crops: list[str] = []

        async def extract(self, page):
            reading = await super().extract(page)
            if reading.forms_on_page:  # the whole page: its names are placed too
                reading = reading.model_copy(update={"first_name": NAME_UNCLEAR})
            return reading

        async def read_name(self, crop: PageImage) -> NameReading:
            self.crops.append(crop.file_id)
            return READ_UP_CLOSE.model_copy(deep=True)

    provider = Script()

    result = run([upload(2)], provider)

    file_id = result.files[0].file_id
    # Not the whole page: it is about to be cut, and each form is read on its own.
    assert sorted(provider.crops) == [f"{file_id}-f1", f"{file_id}-f2"]
    cut = [f for f in result.forms if f.form.file_id != file_id]
    assert [f.form.fields.first_name.raw for f in cut] == ["ישראל", "ישראל"]
    assert result.failed_pages == []
