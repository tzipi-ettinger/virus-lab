"""The records file: CSV in the columns of SPEC 10, or JSON as a list of Record (D19).

Pure: records in, bytes out. Which records, and the export_log row, are in
storage/review.py.

Owner: B
"""

import csv
import io
import json
from datetime import date

from app.i18n import text_for
from app.rules.review_policy import is_blocking
from app.schemas.api import FormField, Record

# The seven fields in the order of the guidelines (SPEC 10). "central_numbers" is
# the list, the rest are keys of Record.fields.
FIELD_ORDER = (
    "first_name",
    "last_name",
    "national_id",
    "central_numbers",
    "received_date",
    "sender",
    "commitment_number",
)
COLUMNS = (*FIELD_ORDER, "review", "touched", "source_file", "page_number")

# Excel runs a cell that starts with one of these as a formula (CSV injection).
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def to_csv(records: list[Record]) -> bytes:
    """UTF-8 with BOM, so Excel shows Hebrew. Every value is text as it is, so
    leading zeros stay in the file."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(text_for(f"export.columns.{column}") for column in COLUMNS)
    for record in records:
        writer.writerow(_safe_cell(cell) for cell in _row(record))
    return out.getvalue().encode("utf-8-sig")


def to_json(records: list[Record]) -> bytes:
    """The full records, as the API returns them: for a future link to the lab's system."""
    data = [record.model_dump(mode="json") for record in records]
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def export_filename(export_format: str, today: date) -> str:
    return f"records-{today.isoformat()}.{export_format}"


def _row(record: Record) -> list[str]:
    fields = record.fields
    return [
        fields.first_name.value or "",
        fields.last_name.value or "",
        fields.national_id.value or "",
        ", ".join(item.value for item in record.central_numbers if item.value),
        _day_month_year(fields.received_date.value),
        fields.sender.value or "",
        fields.commitment_number.value or "",
        "; ".join(_review_reasons(record)),
        ", ".join(_field_text(name) for name in _touched(record)),
        record.source_file,
        str(record.page_number),
    ]


def _fields(record: Record) -> list[tuple[str, list[FormField]]]:
    """Each of the seven fields with its items: one for a field, any for the list."""
    return [
        (name, record.central_numbers)
        if name == "central_numbers"
        else (name, [getattr(record.fields, name)])
        for name in FIELD_ORDER
    ]


def _review_reasons(record: Record) -> list[str]:
    """Why the record still needs review: empty when it doesn't (SPEC 10).

    Each flagged field's warnings, named by field, then the record's own.
    """
    if not record.needs_review:
        return []
    reasons = [
        f"{_field_text(name)}: {issue.message}"
        for name, items in _fields(record)
        for item in items
        if item.needs_review
        for issue in item.issues
        if is_blocking(issue)
    ]
    reasons += [issue.message for issue in record.issues if is_blocking(issue)]
    return list(dict.fromkeys(reasons))  # two central numbers can say the same thing


def _touched(record: Record) -> list[str]:
    """The fields the user corrected or confirmed, in column order."""
    return [
        name
        for name, items in _fields(record)
        if any(item.corrected or item.confirmed for item in items)
    ]


def _field_text(name: str) -> str:
    return text_for(f"export.fields.{name}")


def _day_month_year(value: str | None) -> str:
    """ISO to DD/MM/YYYY. A missing or invalid date is an empty cell."""
    try:
        return date.fromisoformat(value).strftime("%d/%m/%Y") if value else ""
    except ValueError:
        return ""


def _safe_cell(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value
