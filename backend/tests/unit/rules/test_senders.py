"""Closed senders list (senders.yaml) and matching to it (SPEC 5.5)."""

from collections import Counter

import pytest

from app.rules.senders import load_senders, normalize_sender, sender_names


def codes(issues):
    return [issue.code for issue in issues]


def test_list_has_the_four_health_funds():
    assert {"כללית", "מכבי", "מאוחדת", "לאומית"} <= set(sender_names())


def test_names_are_unique():
    assert [name for name, count in Counter(sender_names()).items() if count > 1] == []


def test_no_alias_points_to_two_senders():
    owners = Counter(key for sender in load_senders() for key in set(sender.keys()))
    assert [key for key, count in owners.items() if count > 1] == []


@pytest.mark.parametrize(
    ("raw", "name"),
    [
        ("לאומית", "לאומית"),
        ("  לאומית ", "לאומית"),
        ("קופת חולים כללית", "כללית"),
        ("מכבי שירותי בריאות", "מכבי"),
        ('המרכז הרפואי האוניברסיטאי ע"ש אדית וולפסון', "וולפסון"),
        ("רמבם", "רמב״ם"),
        ('הקריה הרפואית רמב"ם', "רמב״ם"),
        ("אסף הרופא", "שמיר (אסף הרופא)"),
        ("מרכז רפואי רבין - קמפוס בילינסון", "רבין (בילינסון / השרון)"),
        ("צה״ל", "צה״ל"),
        ("Sheba", "שיבא"),
        ("המרכז הרפואי אסותא רעננה", "אסותא רעננה"),
        # "אסותא אשדוד" is inside it, the longer alias wins.
        ("המרכז הרפואי אסותא אשדוד-כלניות", "אסותא כלניות (אשדוד)"),
        ("בית החולים האוניברסיטאי אסותא אשדוד", "אסותא אשדוד"),
    ],
)
def test_known_sender_maps_to_its_list_name(raw, name):
    assert normalize_sender(raw) == (name, [])


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("מרפאת הדמה", "מרפאת הדמה"),
        # Two different senders in one text: ambiguous, a person decides.
        ("מכבי העמק", "מכבי העמק"),
        # Assuta is a chain; only the specific hospital is on the list.
        ("אסותא", "אסותא"),
        ("  בית   חולים  ", "בית חולים"),
    ],
)
def test_unknown_sender_keeps_the_text_and_is_flagged(raw, kept):
    value, issues = normalize_sender(raw)
    assert (value, codes(issues)) == (kept, ["SENDER_UNKNOWN"])


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_missing_sender_is_not_flagged_here(raw):
    assert normalize_sender(raw) == (None, [])
