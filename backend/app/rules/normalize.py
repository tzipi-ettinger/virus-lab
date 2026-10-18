"""Normalize raw strings into values (SPEC 5). Pure: no I/O, same input, same output.

Each normalize_* function returns (value, issues). value is None when nothing
usable was read; raw is never touched here.

Owner: B
"""

import re

from app.rules.issues import make_issue
from app.schemas.api import Issue


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)


def normalize_national_id(raw: str | None) -> tuple[str | None, list[Issue]]:
    """Digits only, then by length (SPEC 5.2).

    9 stays. 8 gets a leading 0 (common, so info only). 5-7 are zero-padded and
    10 starting with 0 loses that 0: both turn an odd reading into a valid-looking
    ID, so they are flagged. Any other length stays for validators to flag.
    """
    if raw is None:
        return None, []
    digits = digits_only(raw)
    if not digits:
        return None, []
    if len(digits) == 8:
        return "0" + digits, [make_issue("ID_PADDED")]
    if 5 <= len(digits) <= 7:
        return digits.zfill(9), [make_issue("ID_NORMALIZED")]
    if len(digits) == 10 and digits.startswith("0"):
        return digits[1:], [make_issue("ID_NORMALIZED")]
    return digits, []
