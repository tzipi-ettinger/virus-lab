"""User corrections and confirmations through apply_rules (SPEC 7.4)."""

from datetime import date

from app.rules.engine import apply_rules
from app.schemas.api import FormField

TODAY = date(2026, 10, 18)


def codes(field):
    return [issue.code for issue in field.issues]


def corrected(field: FormField, value: str | None) -> FormField:
    return field.model_copy(update={"value": value, "corrected": True, "confirmed": False})


def test_corrected_field_is_normalized_from_the_typed_value(load_form):
    form = load_form("unclear")
    form.fields.national_id = corrected(form.fields.national_id, "11223344")
    field = apply_rules(form, today=TODAY).fields.national_id
    assert (field.raw, field.value, codes(field)) == ("0011223344", "011223344", ["ID_PADDED"])
    assert field.needs_review is False


def test_corrected_unclear_field_is_not_flagged_unclear(load_form):
    form = load_form("unclear")
    form.fields.received_date = corrected(form.fields.received_date, "18/06/2026")
    field = apply_rules(form, today=TODAY).fields.received_date
    assert (field.value, codes(field), field.needs_review) == ("2026-06-18", [], False)


def test_corrected_value_still_goes_through_validation(load_form):
    form = load_form("clean")
    form.fields.national_id = corrected(form.fields.national_id, "011223345")
    field = apply_rules(form, today=TODAY).fields.national_id
    assert (codes(field), field.needs_review) == (["ID_CHECKSUM_INVALID"], True)


def test_clearing_a_required_field_flags_it_missing(load_form):
    form = load_form("clean")
    form.fields.sender = corrected(form.fields.sender, None)
    field = apply_rules(form, today=TODAY).fields.sender
    assert (field.value, codes(field)) == (None, ["REQUIRED_MISSING"])


def test_confirmed_value_keeps_its_issue_without_review(load_form):
    form = load_form("unclear")
    form.central_numbers[0] = form.central_numbers[0].model_copy(update={"confirmed": True})
    item = apply_rules(form, today=TODAY).central_numbers[0]
    assert (item.value, codes(item), item.needs_review) == ("94806", ["CENTRAL_FORMAT"], False)


def test_user_typed_commitment_fills_the_empty_item(load_form):
    form = apply_rules(load_form("no_commitment"), today=TODAY)
    form.commitment_numbers[0] = corrected(form.commitment_numbers[0], " 3317702 ")
    form = apply_rules(form, today=TODAY)
    item = form.commitment_numbers[0]
    assert (item.raw, item.value, codes(item), item.needs_review) == (None, "3317702", [], False)
    assert form.needs_review is False


def test_confirming_the_empty_commitment_resolves_it(load_form):
    form = apply_rules(load_form("no_commitment"), today=TODAY)
    form.commitment_numbers[0] = form.commitment_numbers[0].model_copy(update={"confirmed": True})
    form = apply_rules(form, today=TODAY)
    assert codes(form.commitment_numbers[0]) == ["REQUIRED_MISSING"]
    assert form.needs_review is False
