from datetime import UTC, date, datetime

from app.clock import israel_today


def test_after_midnight_in_israel_it_is_already_tomorrow():
    # 22:30 UTC on 19.10 is 01:30 on 20.10 in Israel (summer time, UTC+3).
    assert israel_today(datetime(2026, 10, 19, 22, 30, tzinfo=UTC)) == date(2026, 10, 20)


def test_in_winter_israel_is_two_hours_ahead():
    # Winter time (UTC+2): 22:30 UTC is 00:30 the next day, 21:30 UTC is still today.
    assert israel_today(datetime(2026, 12, 1, 22, 30, tzinfo=UTC)) == date(2026, 12, 2)
    assert israel_today(datetime(2026, 12, 1, 21, 30, tzinfo=UTC)) == date(2026, 12, 1)


def test_without_an_argument_it_returns_a_date():
    assert isinstance(israel_today(), date)
