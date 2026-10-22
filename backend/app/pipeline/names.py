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

Owner: A
"""

import logging
from dataclasses import replace

from app.extraction.provider import ExtractionProvider, NameReader, ProviderError, QuotaExhausted
from app.pipeline.assemble import form_id
from app.pipeline.boxes import SCALE, Box, as_box
from app.pipeline.ingest import SourcePage
from app.pipeline.orient import OrientedPage
from app.schemas.extraction import NamePart, RawExtraction, RawField

logger = logging.getLogger(__name__)

# Room around the name's boxes, in 0-1000 of the page: for its labels ("שם פרטי",
# "שם משפחה", which tell first from last) and for a box drawn a little off.
PAD_Y = 40
PAD_X = 120


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
    merged = extraction.model_copy(
        update={
            "first_name": merge(extraction.first_name, closer.first_name),
            "last_name": merge(extraction.last_name, closer.last_name),
        }
    )
    return replace(oriented, extraction=merged, calls=oriented.calls + 1)


def name_area(extraction: RawExtraction) -> Box | None:
    """The first and last name's boxes together, with room around them. None when
    the page read placed neither."""
    boxes = [
        box
        for field in (extraction.first_name, extraction.last_name)
        if field.status != "not_found" and (box := as_box(field.box_2d))
    ]
    if not boxes:
        return None
    return Box(
        top=max(0, min(box.top for box in boxes) - PAD_Y),
        left=max(0, min(box.left for box in boxes) - PAD_X),
        bottom=min(SCALE, max(box.bottom for box in boxes) + PAD_Y),
        right=min(SCALE, max(box.right for box in boxes) + PAD_X),
    )


def merge(page_read: RawField, closer: NamePart) -> RawField:
    """One name part after both reads. The box stays the page read's: the crop's
    coordinates mean nothing on the page."""
    value = " ".join((closer.value or "").split())
    if closer.status == "found" and value:
        return page_read.model_copy(
            update={"value": value, "status": "found", "evidence": closer.evidence}
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
