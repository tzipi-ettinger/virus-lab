"""Extraction -> contract fields (raw, model_status, evidence and box only).

The only place that knows both schemas/extraction.py and schemas/api.py,
so a change in the extraction schema never reaches the rules.

The output is what apply_rules expects (tests/fixtures/rules/README.md): `raw`
holds what the model read, `value` is left empty for the rules to normalize, and
there are no issues or flags yet, except the page-level ROTATION_UNRESOLVED and
SEVERAL_FORMS_ON_PAGE.

Owner: A
"""

from app.pipeline.boxes import as_box
from app.pipeline.orient import OrientedPage
from app.rules.issues import make_issue
from app.schemas.api import FieldBox, Form, FormField, FormFields, Issue
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
        issues=_issues(page),
        needs_review=False,
    )


def _issues(page: OrientedPage) -> list[Issue]:
    issues = [make_issue("ROTATION_UNRESOLVED")] if page.unresolved else []
    # The model saw several forms and read only the first (prompt v8), and the page
    # got here uncut: split.py found the boxes doubtful, or it is a form already cut
    # out of a page. The others were never read, and only a person can tell.
    if len(page.extraction.forms_on_page) > 1:
        issues.append(make_issue("SEVERAL_FORMS_ON_PAGE"))
    return issues


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
    """The model's box_2d as a FieldBox, or None when it can't be drawn: a box only
    marks something that was read, and only a real rectangle on the page (as_box)."""
    box = as_box(raw.box_2d) if status != "not_found" else None
    if box is None:
        return None
    return FieldBox(page_number=page_number, **box._asdict())
