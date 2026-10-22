"""The patient's name, read a second time: only the name, cut out and enlarged.

On the sample pages the name is small handwritten Hebrew cursive. Read on the
whole page, 1 of 96 name parts came back right, and 22 wrong ones came back
"found", saved without review ("יוסף סואעד" where the page says "ישראל ישראלי";
measurement 22.10). Cut out around the name and enlarged, the same model read
them right, or said it couldn't tell (spike on 5 pages, 22.10).

So every page read upright whose first read placed a name, sure or not, is read
again from a crop around it (ingest.render_crop), and the crop decides:
- sure of a name: that name, "found", even over a different name the page read
  was sure of (in the measurement, the page read's sure names were the wrong ones);
- not sure: "unclear", value null, so a person reads it from the page;
- no name in the crop: "unclear" if the page read was sure of one there, since that
  name was likely made up; otherwise the page read stays.
That is one more model call per page. If it fails, the page read stays: the page
was read, and losing it to the second call would cost more than it saves.

"Sure" is checked here, not taken from the model: the crop first lists the letters
it sees, and a name counts as found only when those letters spell it, every one
read and Hebrew (spelled()). A model that slides into a common name that looks
alike says "found" about it, but rarely lists its letters to match.

A name the crop leaves unclear gets one more, deeper look at the same crop
(thinking level high): one more call, only for those pages. The deeper look
must pass the same check, and a part it isn't sure of keeps the first look's
reading: thinking longer finds letters, it never lowers the bar.

Owner: A
"""

import logging
from dataclasses import replace

from app.extraction.provider import ExtractionProvider, NameReader, ProviderError, QuotaExhausted
from app.pipeline.assemble import form_id
from app.pipeline.ingest import SourcePage
from app.pipeline.orient import OrientedPage
from app.schemas.extraction import NamePart, NameReading, RawExtraction, RawField

logger = logging.getLogger(__name__)

# Room around the name's boxes, in 0-1000 of the page: for its labels ("שם פרטי",
# "שם משפחה", which tell first from last) and for a box drawn a little off.
PAD_Y = 40
PAD_X = 120

Box = tuple[int, int, int, int]  # (top, left, bottom, right), 0-1000


async def read_name_closer(
    provider: ExtractionProvider, page: SourcePage, oriented: OrientedPage
) -> OrientedPage:
    """The page with its name read again from a crop, or as it was when there is
    nothing to crop or the provider can't read a crop (fake)."""
    if not isinstance(provider, NameReader) or oriented.unresolved:
        return oriented  # a sideways crop would be cut from the wrong place
    extraction = oriented.extraction
    area = name_area(extraction)
    if area is None:
        return oriented
    crop = await page.render_crop_async(oriented.applied_rotation, area)
    try:
        closer = await provider.read_name(crop)
    except (ProviderError, QuotaExhausted) as exc:
        # QuotaExhausted too: this page was read. The next page's call stops the batch.
        page_id = form_id(page.file_id, page.page_number)
        logger.warning("name not read again: %s (%s)", page_id, type(exc).__name__)
        return replace(oriented, calls=oriented.calls + 1)
    calls = oriented.calls + 1
    merged = _merge_both(extraction, closer)
    if _needs_review(merged):
        calls += 1
        try:
            deeper = await provider.read_name(crop, deep=True)
        except (ProviderError, QuotaExhausted) as exc:
            # The first look stands: it was read, and is already sent to review.
            page_id = form_id(page.file_id, page.page_number)
            logger.warning("name not read deeper: %s (%s)", page_id, type(exc).__name__)
        else:
            merged = _merge_both(extraction, _surer(closer, deeper))
    return replace(oriented, extraction=merged, calls=calls)


def _merge_both(extraction: RawExtraction, closer: NameReading) -> RawExtraction:
    return extraction.model_copy(
        update={
            "first_name": merge(extraction.first_name, closer.first_name),
            "last_name": merge(extraction.last_name, closer.last_name),
        }
    )


def _needs_review(extraction: RawExtraction) -> bool:
    return "unclear" in (extraction.first_name.status, extraction.last_name.status)


def _surer(first: NameReading, deeper: NameReading) -> NameReading:
    """Each part from the deeper look where it is sure, else from the first look."""
    return NameReading(
        first_name=deeper.first_name if is_sure(deeper.first_name) else first.first_name,
        last_name=deeper.last_name if is_sure(deeper.last_name) else first.last_name,
    )


def is_sure(closer: NamePart) -> bool:
    """A crop's name part that counts as found: said found, and its letters spell it."""
    return closer.status == "found" and spelled(_tidy(closer.value), closer.letters)


def _tidy(value: str | None) -> str:
    return " ".join((value or "").split())


def name_area(extraction: RawExtraction) -> Box | None:
    """The first and last name's boxes together, with room around them. None when
    the page read placed neither."""
    boxes = [
        field.box_2d
        for field in (extraction.first_name, extraction.last_name)
        if field.status != "not_found" and _is_box(field.box_2d)
    ]
    if not boxes:
        return None
    return (
        max(0, min(box[0] for box in boxes) - PAD_Y),
        max(0, min(box[1] for box in boxes) - PAD_X),
        min(1000, max(box[2] for box in boxes) + PAD_Y),
        min(1000, max(box[3] for box in boxes) + PAD_X),
    )


def merge(page_read: RawField, closer: NamePart) -> RawField:
    """One name part after both reads. The box stays the page read's: the crop's
    coordinates mean nothing on the page."""
    if is_sure(closer):
        return page_read.model_copy(
            update={"value": _tidy(closer.value), "status": "found", "evidence": closer.evidence}
        )
    if closer.status == "not_found" and page_read.status != "found":
        return page_read  # nothing new: the page read wasn't sure of a name either
    # Not sure up close, or no name where the page read was sure of one: a person reads it.
    return page_read.model_copy(
        update={
            "value": None,
            "status": "unclear",
            "evidence": closer.evidence or page_read.evidence,
        }
    )


def spelled(value: str, letters: list[str]) -> bool:
    """Whether `letters` spell `value`, one Hebrew letter each and none unread.

    Spaces don't count, and a final letter (ם) matches its plain form (מ), so a
    name isn't sent to review for writing a letter's other form. A name in Latin
    letters goes to review too: cursive Hebrew can look Latin ("plce" for ישראל).
    """
    letters = [letter for letter in letters if letter.strip()]  # a space between words
    if not value or not letters:
        return False
    if any(len(letter) != 1 or not _is_name_letter(letter) for letter in letters):
        return False  # "?" for a letter not read, or more than one letter in an item
    written = value.replace(" ", "")
    if not all(_is_name_letter(char) for char in written):
        return False
    return _plain(written) == _plain("".join(letters))


# Hebrew letters (finals included), and the geresh and hyphen names are written with.
_NAME_MARKS = frozenset("'׳-")
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def _is_name_letter(char: str) -> bool:
    return "א" <= char <= "ת" or char in _NAME_MARKS


def _plain(text: str) -> str:
    return text.translate(_FINALS)


def _is_box(box: list[int] | None) -> bool:
    if box is None or len(box) != 4:
        return False
    top, left, bottom, right = box
    return 0 <= top < bottom <= 1000 and 0 <= left < right <= 1000
