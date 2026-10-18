"""Decides needs_review (SPEC 7.3, SPEC 8). The model never decides this.

Owner: B
"""

from app.rules.issues import make_issue
from app.schemas.api import FormField, Issue


def is_blocking(issue: Issue) -> bool:
    """Warnings and errors need a person; info is only shown."""
    return issue.severity != "info"


def review_field(
    field: FormField, value: str | None, issues: list[Issue], *, required: bool
) -> FormField:
    """Final value, issues and needs_review for one field or list item.

    - unclear and not corrected: no value, only FIELD_UNCLEAR (SPEC 7.3).
    - required, nothing read and nothing else wrong: REQUIRED_MISSING.
    - needs_review = a warning or error that the user hasn't confirmed. Confirming
      keeps the issues on screen (SPEC 7.4), including on an empty field (D3).
    """
    if field.model_status == "unclear" and not field.corrected:
        value, issues = None, [make_issue("FIELD_UNCLEAR")]
    else:
        issues = list(issues)
    if value is None and required and not any(is_blocking(issue) for issue in issues):
        issues.append(make_issue("REQUIRED_MISSING"))
    needs_review = any(is_blocking(issue) for issue in issues) and not field.confirmed
    return field.model_copy(update={"value": value, "issues": issues, "needs_review": needs_review})
