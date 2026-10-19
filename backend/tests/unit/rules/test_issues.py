from typing import get_args

from app.i18n import load_texts
from app.rules.issues import CATALOG, make_issue
from app.schemas.api import IssueCode


def test_every_issue_code_has_a_severity():
    assert set(CATALOG) == set(get_args(IssueCode))


def test_every_issue_code_has_a_hebrew_message():
    assert set(load_texts("he")["issues"]) == set(get_args(IssueCode))


def test_page_grouping_uncertain_is_a_warning():
    # A1 in #15: a page that may belong to another patient's form needs a person.
    assert make_issue("PAGE_GROUPING_UNCERTAIN").severity == "warning"


def test_make_issue_uses_the_catalog_and_the_texts():
    issue = make_issue("ID_PADDED")
    assert (issue.code, issue.severity, issue.message) == ("ID_PADDED", "info", "הושלם 0 מוביל")
