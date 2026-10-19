import pytest

from app.i18n import text_for


def test_text_for_reads_a_nested_key():
    assert text_for("issues.DATE_INVALID") == "תאריך לא תקין"


@pytest.mark.parametrize("key", ["issues.NO_SUCH_CODE", "nothing", "issues"])
def test_a_missing_key_or_a_section_raises(key):
    # "issues" is a section, not a text: returning the dict would show it to a user.
    with pytest.raises(KeyError):
        text_for(key)
