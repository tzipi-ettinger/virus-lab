"""Today's date in Israel, for the rules (received date not in the future).

The lab is in Israel, and a server usually runs on UTC: between midnight and
03:00 Israel time its date is still yesterday, so a form received today would be
flagged DATE_OUT_OF_RANGE. Every caller of apply_rules passes israel_today().

Owner: A
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

# Needs the tzdata package on Windows, which has no time zone database of its own.
ISRAEL = ZoneInfo("Asia/Jerusalem")


def israel_today(now: datetime | None = None) -> date:
    """`now` is for tests; it must be timezone-aware."""
    return (now or datetime.now(ISRAEL)).astimezone(ISRAEL).date()
