"""build_records(form): one record per commitment number (SPEC 7.1, D2).

Takes a form that apply_rules already ran on. Storage adds the IDs, version
and timestamps when it saves a RecordDraft as a Record.

Owner: B
"""

from pydantic import BaseModel

from app.rules.review_policy import is_blocking
from app.schemas.api import Form, FormField, FormFields, Issue, RecordFields


class RecordDraft(BaseModel):
    """A Record before it is saved: everything the rules decide, nothing storage decides."""

    commitment_index: int
    fields: RecordFields
    central_numbers: list[FormField]
    issues: list[Issue]
    needs_review: bool


def build_records(form: Form) -> list[RecordDraft]:
    """Every record gets its own copy of the shared fields and of all central numbers.

    No cross product: 2 commitments and 3 central numbers give 2 records, not 6.
    apply_rules leaves at least one commitment item (an empty, flagged one when
    the form has none), so every form gives at least one record.
    """
    shared = {name: getattr(form.fields, name) for name in FormFields.model_fields}
    records = []
    for index, commitment in enumerate(form.commitment_numbers):
        fields = RecordFields(**shared, commitment_number=commitment).model_copy(deep=True)
        central_numbers = [item.model_copy(deep=True) for item in form.central_numbers]
        issues = [issue.model_copy() for issue in form.issues]
        record_fields = [getattr(fields, name) for name in RecordFields.model_fields]
        needs_review = any(field.needs_review for field in record_fields + central_numbers) or any(
            is_blocking(issue) for issue in issues
        )
        records.append(
            RecordDraft(
                commitment_index=index,
                fields=fields,
                central_numbers=central_numbers,
                issues=issues,
                needs_review=needs_review,
            )
        )
    return records


def blocking_fields(fields: RecordFields, central_numbers: list[FormField]) -> list[str]:
    """Fields that still need review, as named in Problem.blocking_fields.

    e.g. ["national_id", "central_numbers[1]"]. Approve is blocked while this is not empty (D3).
    """
    names = [name for name in RecordFields.model_fields if getattr(fields, name).needs_review]
    names += [
        f"central_numbers[{i}]" for i, item in enumerate(central_numbers) if item.needs_review
    ]
    return names
