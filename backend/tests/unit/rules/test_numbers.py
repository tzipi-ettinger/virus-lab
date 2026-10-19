"""Central and commitment numbers (SPEC 5.3, 5.6) and duplicate removal (SPEC 7.2)."""

import pytest

from app.rules.normalize import (
    dedupe_positions,
    normalize_central_number,
    normalize_commitment_number,
)
from app.rules.validators import validate_central_number


def codes(issues):
    return [issue.code for issue in issues]


@pytest.mark.parametrize(
    ("raw", "value"),
    [("948062", "948062"), ("948 062", "948062"), ("948-062", "948062"), ("", None), (None, None)],
)
def test_normalize_central_number(raw, value):
    assert normalize_central_number(raw) == (value, [])


@pytest.mark.parametrize(
    ("value", "issue_codes"),
    [("948062", []), ("94806", ["CENTRAL_FORMAT"]), ("9480621", ["CENTRAL_FORMAT"]), (None, [])],
)
def test_validate_central_number(value, issue_codes):
    assert codes(validate_central_number(value)) == issue_codes


@pytest.mark.parametrize(
    ("raw", "value", "issue_codes"),
    [
        ("260005102611", "260005102611", []),
        (" 3317702 ", "3317702", []),
        ("606/50364186", "50364186", ["COMMITMENT_PREFIX_REMOVED"]),
        ("606 / 50364186", "50364186", ["COMMITMENT_PREFIX_REMOVED"]),
        ("12/3456", "12/3456", ["COMMITMENT_PREFIX"]),
        ("606/12345", "606/12345", ["COMMITMENT_PREFIX"]),
        ("", None, []),
        (None, None, []),
    ],
)
def test_normalize_commitment_number(raw, value, issue_codes):
    got_value, issues = normalize_commitment_number(raw)
    assert (got_value, codes(issues)) == (value, issue_codes)


@pytest.mark.parametrize(
    ("values", "keep"),
    [
        (["948062", "948063", "948062"], [0, 1]),
        (["948063", "948062", "948063", "948062"], [0, 1]),
        ([None, None, "948062"], [0, 1, 2]),
        ([], []),
    ],
)
def test_dedupe_keeps_first_of_each_in_order(values, keep):
    assert dedupe_positions(values) == keep


def test_prefixed_and_plain_commitment_dedupe_to_one():
    values = [normalize_commitment_number(raw)[0] for raw in ["50364186", "606/50364186"]]
    assert dedupe_positions(values) == [0]
