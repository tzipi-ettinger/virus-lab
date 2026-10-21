"""National ID: normalization by length (SPEC 5.2) and validation (SPEC 8).

IDs here are made up; 011223344 and 000000018 have a valid check digit.
"""

import pytest

from app.rules.normalize import normalize_national_id
from app.rules.validators import israeli_id_checksum_ok, validate_national_id


def codes(issues):
    return [issue.code for issue in issues]


@pytest.mark.parametrize(
    ("raw", "value", "issue_codes"),
    [
        ("011223344", "011223344", []),
        ("11223344", "011223344", ["ID_PADDED"]),
        ("1234567", "001234567", ["ID_NORMALIZED"]),
        ("12345", "000012345", ["ID_NORMALIZED"]),
        ("0011223344", "011223344", ["ID_NORMALIZED"]),
        ("1122334455", "1122334455", []),
        ("1234", "1234", []),
        ("011-223-344", "011223344", []),
        (" 011 223 344 ", "011223344", []),
        ("לא ידוע", None, []),
        (None, None, []),
    ],
)
def test_normalize_national_id(raw, value, issue_codes):
    got_value, issues = normalize_national_id(raw)
    assert (got_value, codes(issues)) == (value, issue_codes)


def test_eight_zeros_are_flagged_after_padding():
    value, issues = normalize_national_id("00000000")
    assert codes(issues + validate_national_id(value)) == ["ID_PADDED", "ID_CHECKSUM_INVALID"]


def test_padding_is_info_and_normalizing_is_a_warning():
    _, padded = normalize_national_id("11223344")
    _, normalized = normalize_national_id("0011223344")
    assert padded[0].severity == "info"
    assert normalized[0].severity == "warning"


@pytest.mark.parametrize(
    ("national_id", "ok"),
    [("011223344", True), ("000000018", True), ("011223345", False), ("123456789", False)],
)
def test_israeli_id_checksum(national_id, ok):
    assert israeli_id_checksum_ok(national_id) is ok


@pytest.mark.parametrize(
    ("value", "issue_codes"),
    [
        ("011223344", []),
        ("011223345", ["ID_CHECKSUM_INVALID"]),
        ("000000000", ["ID_CHECKSUM_INVALID"]),
        ("000000018", []),
        ("1234", ["ID_LENGTH_INVALID"]),
        ("1122334455", ["ID_LENGTH_INVALID"]),
        (None, []),
    ],
)
def test_validate_national_id(value, issue_codes):
    assert codes(validate_national_id(value)) == issue_codes
