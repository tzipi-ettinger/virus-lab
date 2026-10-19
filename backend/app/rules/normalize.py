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
# A time before or after the date (18/06/2026 10:30): read the date, drop the time.
_TIME_AT_EDGE = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?\s+|\s+\d{1,2}:\d{2}(?::\d{2})?$")
# "606/50364186": the sending lab's 3-digit code before a long number. 606 is the
# lab in Karmiel, not part of the number (the team lead, #18).
_LAB_PREFIX = re.compile(r"\d{3}/(\d{6,})")


def digits_only(text: str) -> str:
    return re.sub(r"\D", "", text)


def normalize_name(raw: str | None) -> tuple[str | None, list[Issue]]:
    """Extra spaces only: no translation or transliteration (SPEC 5.1)."""
    return (" ".join((raw or "").split()) or None), []


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

    A time before or after the date is ignored. A date that can't be read, or
    doesn't exist (31/02), gives no value and DATE_INVALID: an empty flagged
    field beats a guessed one.
    """
    text = _TIME_AT_EDGE.sub("", (raw or "").strip())
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


def normalize_central_number(raw: str | None) -> tuple[str | None, list[Issue]]:
    """Digits only (SPEC 5.3). The 6-digit check is in validators."""
    digits = digits_only(raw or "")
    return (digits or None), []


def normalize_commitment_number(raw: str | None) -> tuple[str | None, list[Issue]]:
    """Copied as written (SPEC 5.6), except a lab prefix like 606/ is dropped.

    The dropped prefix is only shown (COMMITMENT_PREFIX_REMOVED, info). Any other /
    is a warning (COMMITMENT_PREFIX), so a person checks it.
    """
    text = re.sub(r"\s*/\s*", "/", (raw or "").strip())
    if not text:
        return None, []
    if match := _LAB_PREFIX.fullmatch(text):
        return match[1], [make_issue("COMMITMENT_PREFIX_REMOVED")]
    if "/" in text:
        return text, [make_issue("COMMITMENT_PREFIX")]
    return text, []


def dedupe_positions(values: list[str | None]) -> list[int]:
    """Positions to keep: the first of each value, in order (SPEC 7.2).

    None (an item that wasn't read) is never a duplicate of anything.
    """
    seen: set[str] = set()
    keep = []
    for position, value in enumerate(values):
        if value is not None:
            if value in seen:
                continue
            seen.add(value)
        keep.append(position)
    return keep
