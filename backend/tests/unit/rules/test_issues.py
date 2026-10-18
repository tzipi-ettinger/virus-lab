from typing import get_args

from app.rules.issues import CATALOG, make_issue
from app.schemas.api import IssueCode


def test_every_issue_code_has_a_message():
    assert set(CATALOG) == set(get_args(IssueCode))


def test_make_issue_uses_the_catalog():
    issue = make_issue("ID_PADDED")
    assert (issue.code, issue.severity, issue.message) == ("ID_PADDED", "info", "הושלם 0 מוביל")
