"""Issue catalog: each code's severity (SPEC 8).

The message the user sees is in i18n/he.yaml, under issues.<code>.

Owner: B
"""

from app.i18n import text_for
from app.schemas.api import Issue, IssueCode, Severity

CATALOG: dict[IssueCode, Severity] = {
    "FIELD_UNCLEAR": "warning",
    "REQUIRED_MISSING": "warning",
    "ID_CHECKSUM_INVALID": "warning",
    "ID_LENGTH_INVALID": "warning",
    "ID_NORMALIZED": "warning",
    "ID_PADDED": "info",
    "DATE_INVALID": "warning",
    "DATE_OUT_OF_RANGE": "warning",
    "SENDER_UNKNOWN": "warning",
    "CENTRAL_FORMAT": "warning",
    "COMMITMENT_PREFIX": "warning",
    # The sending lab's code (606/), not part of the number: shown, not blocking (#18).
    "COMMITMENT_PREFIX_REMOVED": "info",
    "ROTATION_UNRESOLVED": "warning",
    "DUPLICATE_REMOVED": "info",
    "DUPLICATE_RECORD": "warning",
    "PAGE_GROUPING_UNCERTAIN": "warning",
    "SEVERAL_FORMS_ON_PAGE": "warning",
    "EXTRACTION_FAILED": "error",
    "INVALID_FILE": "error",
}


def make_issue(code: IssueCode) -> Issue:
    return Issue(code=code, severity=CATALOG[code], message=text_for(f"issues.{code}"))
