import pytest

from app.rules.text import fold_text


@pytest.mark.parametrize(
    ("text", "folded"),
    [
        ("רמב״ם", "רמבם"),
        ('רמב"ם', "רמבם"),
        ("סנט ג'וזף", "סנט גוזף"),
        ("שִׁיבָּא", "שיבא"),
        ("בית־חולים", "בית חולים"),
        ("אל-מקאסד", "אל מקאסד"),
        ("  המרכז   הרפואי, חיפה. ", "המרכז הרפואי חיפה"),
        ("Sheba", "sheba"),
        ("", ""),
    ],
)
def test_fold_text(text, folded):
    assert fold_text(text) == folded
