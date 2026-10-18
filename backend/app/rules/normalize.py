"""Normalize raw strings into values (SPEC 5). Pure: no I/O, same input, same output.

Each normalize_* function returns (value, issues). value is None when nothing
usable was read; raw is never touched here.

Owner: B
"""

import re
from datetime import date

from app.rules.issues import make_issue
from app.schemas.api import Issue

# 18-06-2026, 18 -06- 2026, 16/6/26, 30.8.26 (SPEC 5.4): day, month, year.
_DMY = re.compile(r"(\d{1,2})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{4}|\d{2})")
# What the date input on the review screen sends.
_ISO = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


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


def normalize_date(raw: str | None) -> tuple[str | None, list[Issue]]:
    """Day-month-year with -, / or . (a 2-digit year means 20YY), or ISO -> ISO YYYY-MM-DD.

    A date that can't be read, or doesn't exist (31/02), gives no value and
    DATE_INVALID: an empty flagged field beats a guessed one.
    """
    text = (raw or "").strip()
    if not text:
        return None, []
    if match := _ISO.fullmatch(text):
        year, month, day = (int(part) for part in match.groups())
    elif match := _DMY.fullmatch(text):
        day, month = int(match[1]), int(match[2])
        year = int(match[3]) + (2000 if len(match[3]) == 2 else 0)
    else:
        return None, [make_issue("DATE_INVALID")]
    try:
        return date(year, month, day).isoformat(), []
    except ValueError:
        return None, [make_issue("DATE_INVALID")]
