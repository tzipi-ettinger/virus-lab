"""Issue catalog: each code's severity and the message the user sees (SPEC 8).

Owner: B
"""

from app.schemas.api import Issue, IssueCode, Severity

CATALOG: dict[IssueCode, tuple[Severity, str]] = {
    "FIELD_UNCLEAR": ("warning", "הערך לא קריא במקור — יש להשלים ידנית"),
    "REQUIRED_MISSING": ("warning", "לא נמצא בטופס — יש לבדוק"),
    "ID_CHECKSUM_INVALID": ("warning", "מספר ת״ז לא תקין"),
    "ID_LENGTH_INVALID": ("warning", "מספר ת״ז באורך לא תקין"),
    "ID_NORMALIZED": (
        "warning",
        "מספר ת״ז נקרא באורך חריג ותוקן אוטומטית — יש לוודא מול המקור",
    ),
    "ID_PADDED": ("info", "הושלם 0 מוביל"),
    "DATE_INVALID": ("warning", "תאריך לא תקין"),
    "DATE_OUT_OF_RANGE": ("warning", "תאריך לא סביר"),
    "SENDER_UNKNOWN": ("warning", "גורם שולח לא מוכר"),
    "CENTRAL_FORMAT": ("warning", "מספר מרכזי בפורמט חריג"),
    "COMMITMENT_PREFIX": ("warning", "מספר התחייבות עם קידומת — יש לוודא"),
    "ROTATION_UNRESOLVED": ("warning", "העמוד סרוק בכיוון חריג — יש לבדוק את כל השדות"),
    "DUPLICATE_REMOVED": ("info", "הוסרה כפילות"),
    "DUPLICATE_RECORD": ("warning", "מספר ההתחייבות כבר קיים ברשומה אחרת — יש לבדוק"),
    "PAGE_GROUPING_UNCERTAIN": ("warning", "עמוד בלי מספר מרכזי שלא תואם לטופס הקודם — יש לבדוק"),
    "EXTRACTION_FAILED": ("error", "הקריאה נכשלה — נסי שוב"),
    "INVALID_FILE": ("error", "לא ניתן לקרוא את הקובץ"),
}


def make_issue(code: IssueCode) -> Issue:
    severity, message = CATALOG[code]
    return Issue(code=code, severity=severity, message=message)
