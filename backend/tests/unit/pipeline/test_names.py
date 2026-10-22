import asyncio

import pymupdf
import pytest

from app.extraction.provider import PageImage, ProviderError, QuotaExhausted
from app.pipeline.ingest import split_pages
from app.pipeline.names import PAD_X, PAD_Y, merge, name_area, read_name_closer
from app.pipeline.orient import OrientedPage
from app.schemas.extraction import NamePart, NameReading, RawExtraction, RawField

EMPTY = RawField(value=None, status="not_found", evidence=None)
FIRST_BOX = [300, 500, 320, 600]
LAST_BOX = [300, 200, 320, 400]


def name(value: str | None, status: str = "found", box: list[int] | None = FIRST_BOX) -> RawField:
    return RawField(value=value, status=status, evidence="שם", box_2d=box)


def closer(value: str | None, status: str = "found") -> NamePart:
    return NamePart(value=value, status=status, evidence="בהגדלה")


def reading(first: RawField, last: RawField) -> RawExtraction:
    return RawExtraction(
        page_rotation_degrees=0,
        form_type="hmo_form",
        first_name=first,
        last_name=last,
        national_id=RawField(value="11223344", status="found", evidence="ת.ז."),
        received_date=EMPTY,
        sender=EMPTY,
        central_numbers=[],
        commitment_numbers=[],
    )


def oriented(extraction: RawExtraction, *, rotation: int = 0, unresolved: bool = False):
    image = PageImage("f1", "forms.pdf", 1, rotation, b"jpeg")
    return OrientedPage(extraction, image, rotation, unresolved=unresolved, calls=1)


@pytest.fixture
def source_page():
    with pymupdf.open() as doc:
        doc.new_page(width=595, height=842)
        pdf = doc.tobytes()
    return split_pages("f1", "forms.pdf", pdf, max_bytes=20_000_000, max_pages=60)[0]


class PagesOnly:
    """Like the fake provider: reads whole pages, not crops."""

    async def extract(self, page: PageImage) -> RawExtraction:
        raise AssertionError("not called here")


class Names(PagesOnly):
    """Answers every crop with `answer`: a NameReading, or an exception to raise."""

    def __init__(self, answer) -> None:
        self.answer = answer
        self.crops: list[PageImage] = []

    async def read_name(self, crop: PageImage) -> NameReading:
        self.crops.append(crop)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


def run(provider, page, read):
    return asyncio.run(read_name_closer(provider, page, read))


def test_a_name_the_page_could_not_read_comes_from_the_crop(source_page):
    page_read = oriented(reading(name(None, "unclear"), name(None, "unclear", LAST_BOX)))
    provider = Names(NameReading(first_name=closer("ישראל"), last_name=closer("ישראלי")))

    result = run(provider, source_page, page_read)

    first, last = result.extraction.first_name, result.extraction.last_name
    assert (first.value, first.status, last.value, last.status) == (
        "ישראל",
        "found",
        "ישראלי",
        "found",
    )
    assert first.box_2d == FIRST_BOX  # the box on the page, not the crop's
    assert result.calls == 2  # the second read counts against the quota too
    assert result.extraction.national_id == page_read.extraction.national_id
    [crop] = provider.crops
    assert crop.jpeg.startswith(b"\xff\xd8")
    assert crop.page_number == 1


def test_the_crop_is_cut_from_the_page_as_the_model_saw_it(source_page):
    page_read = oriented(reading(name("ישראל"), EMPTY), rotation=90)
    provider = Names(NameReading(first_name=closer("ישראל"), last_name=closer(None, "not_found")))

    run(provider, source_page, page_read)

    assert provider.crops[0].rotation == 90


@pytest.mark.parametrize(
    ("page_read", "closer_read", "expected"),
    [
        # Both sure of the same name, spaces aside: it stays found.
        (name("ישראל"), closer("ישראל "), ("ישראל", "found")),
        # Sure of two different names (the page read invented one): a person decides.
        (name("יוסף"), closer("ישראל"), (None, "unclear")),
        # The crop isn't sure: neither is the record, and nothing is guessed.
        (name("יוסף"), closer(None, "unclear"), (None, "unclear")),
        # A crop that says found without a value isn't sure of anything.
        (name("יוסף"), closer("", "found"), (None, "unclear")),
        # No name in the crop: the box may have missed it, the page read stays.
        (name("יוסף"), closer(None, "not_found"), ("יוסף", "found")),
        (name(None, "unclear"), closer(None, "not_found"), (None, "unclear")),
    ],
)
def test_merge(page_read, closer_read, expected):
    merged = merge(page_read, closer_read)

    assert (merged.value, merged.status) == expected
    assert merged.box_2d == page_read.box_2d


@pytest.mark.parametrize(
    ("provider", "page_read"),
    [
        # The fake provider reads pages only.
        (PagesOnly(), oriented(reading(name("ישראל"), EMPTY))),
        # Never upright: the box may be on a sideways image.
        (Names(ProviderError("x")), oriented(reading(name("ישראל"), EMPTY), unresolved=True)),
        # Nothing to cut out.
        (Names(ProviderError("x")), oriented(reading(EMPTY, EMPTY))),
        (Names(ProviderError("x")), oriented(reading(name("ישראל", box=None), EMPTY))),
    ],
)
def test_no_second_read_when_there_is_nothing_to_read_it_from(source_page, provider, page_read):
    assert run(provider, source_page, page_read) is page_read


@pytest.mark.parametrize("error", [ProviderError("x"), QuotaExhausted("x")])
def test_a_failed_second_read_keeps_the_page_read(source_page, error):
    # The page was read: losing it to the second call would cost more than it saves.
    page_read = oriented(reading(name("יוסף"), EMPTY))

    result = run(Names(error), source_page, page_read)

    assert result.extraction == page_read.extraction
    assert result.calls == 2


def test_the_name_area_holds_both_names_with_room_around():
    area = name_area(reading(name("ישראל"), name("ישראלי", box=LAST_BOX)))

    assert area == (300 - PAD_Y, 200 - PAD_X, 320 + PAD_Y, 600 + PAD_X)


def test_the_name_area_stays_on_the_page():
    edge = name("ישראל", box=[5, 950, 30, 1000])

    assert name_area(reading(edge, EMPTY)) == (0, 950 - PAD_X, 30 + PAD_Y, 1000)


@pytest.mark.parametrize(
    "box",
    [None, [1, 2, 3], [320, 500, 300, 600], [300, 500, 320, 1200], [300, 600, 320, 500]],
)
def test_a_box_that_is_not_a_rectangle_on_the_page_is_not_cut(box):
    assert name_area(reading(name("ישראל", box=box), EMPTY)) is None


def test_a_name_not_found_is_not_part_of_the_area():
    not_found = RawField(value=None, status="not_found", evidence=None, box_2d=[0, 0, 999, 999])

    assert name_area(reading(name("ישראל"), not_found)) == (
        300 - PAD_Y,
        500 - PAD_X,
        320 + PAD_Y,
        600 + PAD_X,
    )
