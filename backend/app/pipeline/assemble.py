"""Extraction -> contract fields (raw, model_status, evidence and box only).

The only place that knows both schemas/extraction.py and schemas/api.py,
so a change in the extraction schema never reaches the rules.

The output is what apply_rules expects (tests/fixtures/rules/README.md): `raw`
holds what the model read, `value` is left empty for the rules to normalize, and
there are no issues or flags yet, except the page-level ROTATION_UNRESOLVED.

Owner: A
"""

from app.pipeline.orient import OrientedPage
from app.rules.issues import make_issue
from app.schemas.api import FieldBox, Form, FormField, FormFields
from app.schemas.extraction import RawField


def form_id(file_id: str, page_number: int) -> str:
    # No "#": in a URL it starts the fragment, and the page number would be lost.
    return f"{file_id}-p{page_number}"


def assemble(page: OrientedPage) -> Form:
    """One extracted page as a Form, ready for apply_rules."""
    extraction, image = page.extraction, page.image
    return Form(
        form_id=form_id(image.file_id, image.page_number),
        file_id=image.file_id,
        source_file=image.filename,
        page_number=image.page_number,
        processing_status="ok",
        error=None,
        applied_rotation=page.applied_rotation,
        form_type=extraction.form_type,
        fields=FormFields(
            first_name=_field(extraction.first_name, image.page_number),
            last_name=_field(extraction.last_name, image.page_number),
            national_id=_field(extraction.national_id, image.page_number),
            received_date=_field(extraction.received_date, image.page_number),
            sender=_field(extraction.sender, image.page_number),
        ),
        central_numbers=[_field(item, image.page_number) for item in extraction.central_numbers],
        commitment_numbers=[
            _field(item, image.page_number) for item in extraction.commitment_numbers
        ],
        issues=[make_issue("ROTATION_UNRESOLVED")] if page.unresolved else [],
        needs_review=False,
    )


def _field(raw: RawField, page_number: int) -> FormField:
    status = raw.status
    if status == "not_found" and raw.value:
        # The model contradicts itself: a value it says isn't there. Seen in the first
        # measurement (a case number as a commitment, 20.10), and the rules accepted it
        # unflagged. Unclear sends it to a person, with what it read kept in raw.
        status = "unclear"
    return FormField(
        raw=raw.value,
        value=None,
        model_status=status,
        evidence=raw.evidence,
        issues=[],
        needs_review=False,
        corrected=False,
        confirmed=False,
        box=_box(raw, status, page_number),
    )


def _box(raw: RawField, status: str, page_number: int) -> FieldBox | None:
    """The model's box_2d as a FieldBox, or None when it can't be drawn.

    A box only marks something that was read, and only a real rectangle on the
    page: a wrong length, an edge off the page or a flat box is dropped, never
    fixed up, since a box in the wrong place is worse than none.
    """
    if status == "not_found" or raw.box_2d is None or len(raw.box_2d) != 4:
        return None
    top, left, bottom, right = raw.box_2d
    if not (0 <= top < bottom <= 1000 and 0 <= left < right <= 1000):
        return None
    return FieldBox(page_number=page_number, top=top, left=left, bottom=bottom, right=right)
