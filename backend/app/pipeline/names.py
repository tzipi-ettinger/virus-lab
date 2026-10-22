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
If the crop can't be read at all, the page read stays: the page was read, and
losing it to the second call would cost more than it saves.

"Sure" is checked here, not taken from the model: the crop first lists the letters
it sees, and a name counts as found only when those letters spell it, every one
read and Hebrew (spelled()). A model that slides into a common name that looks
alike says "found" about it, but rarely lists its letters to match.

Letters copied the same way every time still misread cursive: on part 1 (22.10)
the letter check left 11 wrong name parts of 26 found ("ישמעאל", "יששכר" for
"ישראל"). So the crop is read twice, once more with thinking level high, and a
name part is found only when both looks are sure of the same letters (agree()).
A model that guesses reads unclear handwriting differently each time; a name it
really reads comes out the same. If the second look fails, nothing confirms the
first, and its names go to review. That is two more calls per page, not one.

Last, a first name the same as the last name sends both to review: on part 1
that was the model copying one into the other ("ישראל ישראל", 6 of the 11).

Owner: A
"""

import logging
from dataclasses import replace
from typing import TypeGuard

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
    try:
        deeper: NameReading | None = await provider.read_name(crop, deep=True)
    except (ProviderError, QuotaExhausted) as exc:
        page_id = form_id(page.file_id, page.page_number)
        logger.warning("name not read deeper: %s (%s)", page_id, type(exc).__name__)
        deeper = None  # nothing confirms the first look
    merged = extraction.model_copy(
        update={
            "first_name": merge(extraction.first_name, agree(closer.first_name, deeper, "first")),
            "last_name": merge(extraction.last_name, agree(closer.last_name, deeper, "last")),
        }
    )
    return replace(oriented, extraction=_same_name_twice(merged), calls=oriented.calls + 2)


def agree(first: NamePart, deeper: NameReading | None, part: str) -> NamePart:
    """One name part as both looks at the crop have it: found only when both are
    sure of the same letters, and no name only when neither saw one."""
    other = None
    if deeper is not None:
        other = deeper.first_name if part == "first" else deeper.last_name
    if other is not None and is_sure(first) and is_sure(other):
        if _plain(_tidy(first.value)) == _plain(_tidy(other.value)):
            return first
    if first.status == "not_found" and (other is None or other.status == "not_found"):
        return first
    evidence = first.evidence or (other.evidence if other is not None else None)
    return NamePart(letters=[], value=None, status="unclear", evidence=evidence)


def _same_name_twice(extraction: RawExtraction) -> RawExtraction:
    """Both parts to review when the first name is the last name."""
    first, last = extraction.first_name, extraction.last_name
    if not (first.status == last.status == "found" and first.value and last.value):
        return extraction
    if _plain(first.value.replace(" ", "")) != _plain(last.value.replace(" ", "")):
        return extraction
    unclear = {"value": None, "status": "unclear"}
    return extraction.model_copy(
        update={
            "first_name": first.model_copy(update=unclear),
            "last_name": last.model_copy(update=unclear),
        }
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


def _is_box(box: list[int] | None) -> TypeGuard[list[int]]:
    if box is None or len(box) != 4:
        return False
    top, left, bottom, right = box
    return 0 <= top < bottom <= 1000 and 0 <= left < right <= 1000
