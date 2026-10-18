"""Received date: formats found in the samples (SPEC 5.4) and the 2020-today range."""

from datetime import date

import pytest

from app.rules.normalize import normalize_date
from app.rules.validators import validate_received_date

TODAY = date(2026, 10, 18)


def codes(issues):
    return [issue.code for issue in issues]


@pytest.mark.parametrize(
    ("raw", "value"),
    [
        ("18-06-2026", "2026-06-18"),
        ("18 -06- 2026", "2026-06-18"),
        ("16/6/26", "2026-06-16"),
        ("30.8.26", "2026-08-30"),
        ("25.08.26", "2026-08-25"),
        (" 1/1/2026 ", "2026-01-01"),
        ("2026-06-18", "2026-06-18"),
    ],
)
def test_normalize_date_formats(raw, value):
    assert normalize_date(raw) == (value, [])


@pytest.mark.parametrize("raw", ["31/02/2026", "18/13/2026", "18.06", "abc", "2026-02-30"])
def test_unreadable_or_impossible_date_is_empty_and_flagged(raw):
    value, issues = normalize_date(raw)
    assert (value, codes(issues)) == (None, ["DATE_INVALID"])


@pytest.mark.parametrize("raw", [None, "", "  "])
def test_missing_date_is_not_flagged_here(raw):
    # A missing required field is review_policy's job (REQUIRED_MISSING).
    assert normalize_date(raw) == (None, [])


@pytest.mark.parametrize(
    ("value", "issue_codes"),
    [
        ("2026-10-18", []),
        ("2020-01-01", []),
        ("2026-10-19", ["DATE_OUT_OF_RANGE"]),
        ("2019-12-31", ["DATE_OUT_OF_RANGE"]),
        (None, []),
    ],
)
def test_validate_received_date(value, issue_codes):
    assert codes(validate_received_date(value, TODAY)) == issue_codes
