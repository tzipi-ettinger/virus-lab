"""review_field: unclear, missing, confirmed (SPEC 7.3, 7.4, 8)."""

import pytest

from app.rules.issues import make_issue
from app.rules.review_policy import is_blocking, review_field
from app.schemas.api import FormField


def make_field(**overrides) -> FormField:
    base = {
        "raw": "x",
        "value": None,
        "model_status": "found",
        "evidence": None,
        "issues": [],
        "needs_review": False,
        "corrected": False,
        "confirmed": False,
    }
    return FormField(**(base | overrides))


def codes(field):
    return [issue.code for issue in field.issues]


@pytest.mark.parametrize(
    ("code", "blocking"),
    [("ID_PADDED", False), ("DUPLICATE_REMOVED", False), ("ID_NORMALIZED", True)],
)
def test_only_info_is_not_blocking(code, blocking):
    assert is_blocking(make_issue(code)) is blocking


def test_clean_value_needs_no_review():
    field = review_field(make_field(), "011223344", [], required=True)
    assert (field.value, codes(field), field.needs_review) == ("011223344", [], False)


def test_info_issue_is_kept_but_needs_no_review():
    field = review_field(make_field(), "011223344", [make_issue("ID_PADDED")], required=True)
    assert (codes(field), field.needs_review) == (["ID_PADDED"], False)


def test_warning_needs_review():
    field = review_field(make_field(), "94806", [make_issue("CENTRAL_FORMAT")], required=False)
    assert (codes(field), field.needs_review) == (["CENTRAL_FORMAT"], True)


def test_unclear_drops_the_value_and_other_issues():
    field = review_field(
        make_field(raw="0011223344", model_status="unclear"),
        "011223344",
        [make_issue("ID_NORMALIZED")],
        required=True,
    )
    assert (field.raw, field.value, codes(field)) == ("0011223344", None, ["FIELD_UNCLEAR"])
    assert field.needs_review


def test_required_and_missing_is_flagged():
    field = review_field(make_field(raw=None, model_status="not_found"), None, [], required=True)
    assert (codes(field), field.needs_review) == (["REQUIRED_MISSING"], True)


def test_missing_name_is_not_flagged():
    field = review_field(make_field(raw=None, model_status="not_found"), None, [], required=False)
    assert (codes(field), field.needs_review) == ([], False)


def test_invalid_date_is_not_also_missing():
    field = review_field(
        make_field(raw="31/02/26"), None, [make_issue("DATE_INVALID")], required=True
    )
    assert codes(field) == ["DATE_INVALID"]


def test_confirmed_keeps_issues_but_needs_no_review():
    field = review_field(
        make_field(confirmed=True), "94806", [make_issue("CENTRAL_FORMAT")], required=False
    )
    assert (codes(field), field.needs_review) == (["CENTRAL_FORMAT"], False)


def test_confirmed_empty_required_field_needs_no_review():
    empty = make_field(raw=None, model_status="not_found", confirmed=True)
    field = review_field(empty, None, [], required=True)
    assert (codes(field), field.needs_review) == (["REQUIRED_MISSING"], False)


def test_incoming_issues_and_flag_are_ignored():
    stale = make_field(issues=[make_issue("ID_CHECKSUM_INVALID")], needs_review=True)
    field = review_field(stale, "011223344", [], required=True)
    assert (codes(field), field.needs_review) == ([], False)
