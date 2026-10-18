import asyncio

import pymupdf
import pytest

from app.extraction.fake_provider import FIXTURES_DIR, FakeProvider
from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.pipeline.ingest import split_pages
from app.pipeline.orient import extract_upright
from app.schemas.extraction import RawExtraction, RawField

EMPTY = RawField(value=None, status="not_found", evidence=None)


def reading(rotation: int, national_id: str = "11223344") -> RawExtraction:
    return RawExtraction(
        page_rotation_degrees=rotation,
        form_type="hmo_form",
        first_name=EMPTY,
        last_name=EMPTY,
        national_id=RawField(value=national_id, status="found", evidence="ת.ז."),
        received_date=EMPTY,
        sender=EMPTY,
        central_numbers=[],
        commitment_numbers=[],
    )


class ScriptedProvider:
    """Answers call N with script[N]: a rotation to report, or an exception to raise."""

    def __init__(self, *script) -> None:
        self.script = list(script)
        self.seen_rotations: list[int] = []

    async def extract(self, page: PageImage) -> RawExtraction:
        self.seen_rotations.append(page.rotation)
        step = self.script[len(self.seen_rotations) - 1]
        if isinstance(step, Exception):
            raise step
        return reading(step, national_id=f"call{len(self.seen_rotations)}")


def run(provider, page, **kwargs):
    return asyncio.run(extract_upright(provider, page, **kwargs))


def test_an_upright_page_takes_one_call(source_page):
    provider = ScriptedProvider(0)

    result = run(provider, source_page)

    assert (result.calls, result.applied_rotation, result.unresolved) == (1, 0, False)
    assert provider.seen_rotations == [0]


def test_a_turned_page_is_straightened_and_read_again(source_page):
    provider = ScriptedProvider(90, 0)

    result = run(provider, source_page)

    assert provider.seen_rotations == [0, 90]
    assert (result.calls, result.applied_rotation, result.unresolved) == (2, 90, False)
    assert result.extraction.national_id.value == "call2"  # the upright reading wins
    assert result.image.rotation == 90
    assert result.history == (90, 0)


def test_a_wrong_first_guess_is_corrected(source_page):
    # Part 2 p20 in the spike: 180, then 90 (a total of 270), then upright.
    provider = ScriptedProvider(180, 90, 0)

    result = run(provider, source_page)

    assert provider.seen_rotations == [0, 180, 270]
    assert (result.calls, result.applied_rotation, result.unresolved) == (3, 270, False)


def test_a_page_that_never_turns_upright_is_flagged(source_page):
    provider = ScriptedProvider(90, 90, 90, 90)

    result = run(provider, source_page)

    assert result.calls == 3  # never more than MAX_CORRECTIONS + 1
    assert result.unresolved


@pytest.mark.parametrize("odd", [45, 135])
def test_an_odd_rotation_is_not_rendered_but_flagged(source_page, odd):
    provider = ScriptedProvider(odd)

    result = run(provider, source_page)

    assert result.calls == 1
    assert result.unresolved


def test_a_negative_rotation_counts_clockwise(source_page):
    provider = ScriptedProvider(-90, 0)  # -90 == 270

    result = run(provider, source_page)

    assert provider.seen_rotations == [0, 270]
    assert not result.unresolved


def test_a_failed_correction_keeps_the_first_reading(source_page):
    provider = ScriptedProvider(90, ProviderError("עומס"))

    result = run(provider, source_page)

    assert result.extraction.national_id.value == "call1"
    assert (result.calls, result.applied_rotation, result.unresolved) == (1, 0, True)
    assert result.image.rotation == 0  # the preview matches the reading


def test_a_failed_first_call_fails_the_page(source_page):
    provider = ScriptedProvider(ProviderError("עומס"))

    with pytest.raises(ProviderError):
        run(provider, source_page)


def test_quota_exhausted_during_a_correction_stops_everything(source_page):
    provider = ScriptedProvider(90, QuotaExhausted("המכסה היומית נגמרה"))

    with pytest.raises(QuotaExhausted):
        run(provider, source_page)


def test_quota_exhausted_is_not_a_page_error():
    # Otherwise any `except ProviderError` for one page would let the batch keep going.
    assert not issubclass(QuotaExhausted, ProviderError)


def test_with_fake_provider_a_270_page_takes_two_calls():
    provider = FakeProvider()
    fixtures = sorted(FIXTURES_DIR.glob("*.json"))
    misread = fixtures.index(FIXTURES_DIR / "07_sheba_screenshot_misread.json")
    with pymupdf.open() as doc:
        for _ in fixtures:
            doc.new_page(width=595, height=842)
        data = doc.tobytes()
    pages = split_pages("f1", "forms.pdf", data, max_bytes=20_000_000, max_pages=60)
    page = next(
        p
        for p in pages
        if provider.fixture_index(PageImage("f1", "forms.pdf", p.page_number, 0, b"")) == misread
    )

    result = run(provider, page)

    assert (result.calls, result.applied_rotation, result.unresolved) == (2, 270, False)
    assert result.image.rotation == 270
