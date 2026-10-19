"""apply_rules on the four rules fixtures (tests/fixtures/rules/README.md)."""

from datetime import date

import pytest

from app.rules.engine import MISSING_ITEM, apply_rules
from app.rules.issues import make_issue
from app.schemas.api import Form, FormFields

TODAY = date(2026, 10, 18)


def summary(form: Form) -> dict:
    """field -> (value, issue codes, needs_review); lists as lists of those."""

    def one(field):
        return (field.value, [issue.code for issue in field.issues], field.needs_review)

    out = {name: one(getattr(form.fields, name)) for name in FormFields.model_fields}
    out["central_numbers"] = [one(item) for item in form.central_numbers]
    out["commitment_numbers"] = [one(item) for item in form.commitment_numbers]
    return out


def test_clean(load_form):
    form = apply_rules(load_form("clean"), today=TODAY)
    got = summary(form)
    assert got["national_id"] == ("011223344", ["ID_PADDED"], False)
    assert got["received_date"] == ("2026-06-18", [], False)
    assert got["sender"] == ("מכבי", [], False)
    assert got["central_numbers"] == [("948062", [], False)]
    assert got["commitment_numbers"] == [("260005102632", [], False)]
    assert form.needs_review is False


def test_multi_values(load_form):
    form = apply_rules(load_form("multi_values"), today=TODAY)
    got = summary(form)
    assert got["received_date"] == ("2026-08-30", [], False)
    assert got["central_numbers"] == [
        ("948062", ["DUPLICATE_REMOVED"], False),
        ("948063", [], False),
    ]
    assert got["commitment_numbers"] == [
        ("260005102611", [], False),
        ("50364186", ["COMMITMENT_PREFIX"], True),
    ]
    assert form.commitment_numbers[1].raw == "606/50364186"
    assert form.needs_review is True


def test_unclear(load_form):
    form = apply_rules(load_form("unclear"), today=TODAY)
    got = summary(form)
    assert got["first_name"] == (None, ["FIELD_UNCLEAR"], True)
    assert got["national_id"] == ("011223344", ["ID_NORMALIZED"], True)
    assert got["received_date"] == (None, ["FIELD_UNCLEAR"], True)
    assert got["sender"] == ("מרפאת הדמה", ["SENDER_UNKNOWN"], True)
    assert got["central_numbers"] == [("94806", ["CENTRAL_FORMAT"], True)]
    assert form.needs_review is True


def test_no_commitment_gets_one_empty_flagged_item(load_form):
    form = apply_rules(load_form("no_commitment"), today=TODAY)
    assert summary(form)["commitment_numbers"] == [(None, ["REQUIRED_MISSING"], True)]
    assert form.commitment_numbers[0].raw is None
    assert form.needs_review is True


def test_empty_central_list_is_flagged(load_form):
    form = load_form("clean")
    form.central_numbers = []
    assert summary(apply_rules(form, today=TODAY))["central_numbers"] == [
        (None, ["REQUIRED_MISSING"], True)
    ]


def test_several_empty_items_get_one_required_missing(load_form):
    form = load_form("clean")
    form.central_numbers = [MISSING_ITEM, MISSING_ITEM, MISSING_ITEM]
    ruled = apply_rules(form, today=TODAY)
    assert summary(ruled)["central_numbers"] == [
        (None, ["REQUIRED_MISSING"], True),
        (None, [], False),
        (None, [], False),
    ]
    assert ruled.needs_review is True
    assert apply_rules(ruled, today=TODAY) == ruled


def test_unclear_first_item_is_flagged_without_required_missing(load_form):
    form = load_form("clean")
    form.central_numbers = [
        MISSING_ITEM.model_copy(update={"model_status": "unclear"}),
        MISSING_ITEM,
    ]
    assert summary(apply_rules(form, today=TODAY))["central_numbers"] == [
        (None, ["FIELD_UNCLEAR"], True),
        (None, [], False),
    ]


def test_raw_never_changes(load_form, fixture_names):
    for name in fixture_names:
        before = load_form(name)
        after = apply_rules(before, today=TODAY)
        for field_name in FormFields.model_fields:
            assert getattr(after.fields, field_name).raw == getattr(before.fields, field_name).raw
        before_raws = {item.raw for item in before.central_numbers + before.commitment_numbers}
        after_raws = {item.raw for item in after.central_numbers + after.commitment_numbers}
        assert after_raws - {None} <= before_raws


@pytest.mark.parametrize("name", ["clean", "multi_values", "unclear", "no_commitment"])
def test_running_twice_changes_nothing(load_form, name):
    once = apply_rules(load_form(name), today=TODAY)
    assert apply_rules(once, today=TODAY) == once


def test_form_level_warning_needs_review(load_form):
    form = load_form("clean")
    form.issues = [make_issue("ROTATION_UNRESOLVED")]
    assert apply_rules(form, today=TODAY).needs_review is True


def test_failed_page_is_left_alone(load_form):
    form = load_form("clean").model_copy(update={"processing_status": "error"})
    assert apply_rules(form, today=TODAY) == form
