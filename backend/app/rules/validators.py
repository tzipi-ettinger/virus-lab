"""Check normalized values and return issues (SPEC 5, SPEC 8). Pure: no I/O.

Each validate_* function takes the normalized value (None = nothing read) and
returns the issues it finds; a missing value is review_policy's job, not ours.

Owner: B
"""

from datetime import date

from app.rules.issues import make_issue
from app.schemas.api import Issue

# A received date before this is more likely a misread than a real sample (SPEC 5.4).
EARLIEST_RECEIVED_DATE = date(2020, 1, 1)


def israeli_id_checksum_ok(national_id: str) -> bool:
    """Ministry of Interior check digit over 9 digits: weights 1,2,1,2..., digit sums."""
    total = 0
    for position, char in enumerate(national_id):
        product = int(char) * (1 if position % 2 == 0 else 2)
        total += product - 9 if product > 9 else product
    return total % 10 == 0


def validate_national_id(value: str | None) -> list[Issue]:
    if value is None:
        return []
    if len(value) != 9 or not value.isdigit():
        return [make_issue("ID_LENGTH_INVALID")]
    if not israeli_id_checksum_ok(value):
        return [make_issue("ID_CHECKSUM_INVALID")]
    return []


def validate_received_date(value: str | None, today: date) -> list[Issue]:
    """value is ISO (from normalize_date). today is passed in so the rules stay pure."""
    if value is None:
        return []
    if not EARLIEST_RECEIVED_DATE <= date.fromisoformat(value) <= today:
        return [make_issue("DATE_OUT_OF_RANGE")]
    return []
