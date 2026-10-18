"""apply_rules(form) -> form: the only entry point to the rules (SPEC 9.6).

Runs normalize -> validators -> review_policy on every field. Pure: no I/O, and
today is passed in, so the same form always gives the same result. Called after
extraction (pipeline/service.py) and on every correction or approve.

Owner: B
"""

from collections.abc import Callable
from datetime import date
from functools import partial

from app.rules.issues import make_issue
from app.rules.normalize import (
    dedupe_positions,
    normalize_central_number,
    normalize_commitment_number,
    normalize_date,
    normalize_name,
    normalize_national_id,
)
from app.rules.review_policy import is_blocking, review_field
from app.rules.senders import normalize_sender
from app.rules.validators import (
    validate_central_number,
    validate_national_id,
    validate_received_date,
)
from app.schemas.api import Form, FormField, FormFields, Issue

Normalizer = Callable[[str | None], tuple[str | None, list[Issue]]]
Validator = Callable[[str | None], list[Issue]]

# An item that stands for "nothing was found": a required list with no values
# gets one, so the screen has a place to type the number (and to confirm it empty).
MISSING_ITEM = FormField(
    raw=None,
    value=None,
    model_status="not_found",
    evidence=None,
    issues=[],
    needs_review=False,
    corrected=False,
    confirmed=False,
)


def _no_check(value: str | None) -> list[Issue]:
    return []


def _rule_field(
    field: FormField, normalize: Normalizer, validate: Validator, *, required: bool
) -> FormField:
    value, issues = normalize(field.raw)
    return review_field(field, value, issues + validate(value), required=required)


def _rule_list(
    items: list[FormField], normalize: Normalizer, validate: Validator
) -> list[FormField]:
    """Rule every item, drop repeated values (SPEC 7.2), and make sure one item is left.

    Items are required only when none of them has a value.
    """
    items = items or [MISSING_ITEM]
    ruled = [_rule_field(item, normalize, validate, required=False) for item in items]
    keep = dedupe_positions([item.value for item in ruled])
    if not any(ruled[position].value for position in keep):
        ruled = [_rule_field(item, normalize, validate, required=True) for item in items]
    kept = {position: ruled[position] for position in keep}
    first_with_value = {item.value: position for position, item in reversed(kept.items())}
    for position, item in enumerate(ruled):
        removed = position not in kept
        # DUPLICATE_REMOVED is history: keep it when the rules run again.
        carried = any(issue.code == "DUPLICATE_REMOVED" for issue in items[position].issues)
        if removed or carried:
            target = first_with_value[item.value] if removed else position
            if not any(i.code == "DUPLICATE_REMOVED" for i in kept[target].issues):
                kept[target].issues.append(make_issue("DUPLICATE_REMOVED"))
    return list(kept.values())


def apply_rules(form: Form, *, today: date) -> Form:
    if form.processing_status == "error":
        return form
    fields = form.fields
    ruled_fields = FormFields(
        first_name=_rule_field(fields.first_name, normalize_name, _no_check, required=False),
        last_name=_rule_field(fields.last_name, normalize_name, _no_check, required=False),
        national_id=_rule_field(
            fields.national_id, normalize_national_id, validate_national_id, required=True
        ),
        received_date=_rule_field(
            fields.received_date,
            normalize_date,
            partial(validate_received_date, today=today),
            required=True,
        ),
        sender=_rule_field(fields.sender, normalize_sender, _no_check, required=True),
    )
    central_numbers = _rule_list(
        form.central_numbers, normalize_central_number, validate_central_number
    )
    commitment_numbers = _rule_list(form.commitment_numbers, normalize_commitment_number, _no_check)
    all_fields = [
        *(getattr(ruled_fields, name) for name in FormFields.model_fields),
        *central_numbers,
        *commitment_numbers,
    ]
    needs_review = any(field.needs_review for field in all_fields) or any(
        is_blocking(issue) for issue in form.issues
    )
    return form.model_copy(
        update={
            "fields": ruled_fields,
            "central_numbers": central_numbers,
            "commitment_numbers": commitment_numbers,
            "needs_review": needs_review,
        }
    )
