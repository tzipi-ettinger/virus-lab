"""Rotation loop.

The model reports the clockwise rotation a page still needs. Its first guess is
not reliable (it said 90 and 270 for the same page), but once the page is turned
it sees the result and corrects itself: on part 2 p20 it said 180, then 90, then
0. So we keep turning until it says 0, at most MAX_CORRECTIONS times, and flag
the page if it never does.

Owner: A
"""

from dataclasses import dataclass

from app.extraction.provider import ExtractionProvider, PageImage, ProviderError
from app.pipeline.ingest import ROTATIONS, SourcePage
from app.schemas.extraction import RawExtraction

# Two corrections cover a wrong first guess (seen in the spike): 3 calls at most.
MAX_CORRECTIONS = 2


@dataclass(frozen=True)
class OrientedPage:
    extraction: RawExtraction
    image: PageImage  # the image the extraction was read from, for the preview
    applied_rotation: int
    unresolved: bool  # the model never reported the page upright: check every field
    calls: int  # failed calls included: they count against the quota too
    history: tuple[int, ...] = ()  # rotation the model asked for, per answered call


async def extract_upright(
    provider: ExtractionProvider, page: SourcePage, *, max_corrections: int = MAX_CORRECTIONS
) -> OrientedPage:
    """Extract one page, turning it until the model reports it upright.

    The first call's errors propagate (the page failed). If a correction call
    fails, the last good result is kept and flagged unresolved, since a sideways
    reading is still more than nothing. QuotaExhausted always propagates: the
    batch has to stop.
    """
    image = await page.render_async(0)
    extraction = await provider.extract(image)
    applied, calls, history = 0, 1, [extraction.page_rotation_degrees]
    tried = {0}

    for _ in range(max_corrections):
        needed = extraction.page_rotation_degrees % 360
        if needed == 0 or needed not in ROTATIONS:
            break
        target = (applied + needed) % 360
        if target in tried:  # the model is going in circles: a call would teach nothing new
            break
        tried.add(target)
        turned = await page.render_async(target)
        calls += 1
        try:
            corrected = await provider.extract(turned)
        except ProviderError:  # QuotaExhausted is not one: it propagates
            break
        applied, image, extraction = turned.rotation, turned, corrected
        history.append(extraction.page_rotation_degrees)

    return OrientedPage(
        extraction=extraction,
        image=image,
        applied_rotation=applied,
        unresolved=extraction.page_rotation_degrees % 360 != 0,
        calls=calls,
        history=tuple(history),
    )
