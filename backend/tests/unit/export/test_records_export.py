"""The records file: CSV columns of SPEC 10 and JSON (Dev-B plan B1.9). Synthetic data only."""

import csv
import io
import json
from datetime import UTC, date, datetime

from app.export.records_export import export_filename, to_csv, to_json
from app.rules.issues import make_issue
from app.schemas.api import FormField, Record, RecordFields

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
HEADER = [
    "שם פרטי",
    "שם משפחה",
    "מספר תעודת זהות",
    "מספר מרכזי",
    "תאריך קבלת הדגימה",
    "גורם שולח",
    "מספר התחייבות",
    "לבדיקה",
    "תוקן / אושר ידנית",
    "קובץ מקור",
    "עמוד",
]


def field(value, *, issues=(), needs_review=False, corrected=False, confirmed=False):
    return FormField(
        raw=value,
        value=value,
        model_status="found" if value else "not_found",
        evidence=None,
        issues=[make_issue(code) for code in issues],
        needs_review=needs_review,
        corrected=corrected,
        confirmed=confirmed,
    )


def record(**fields):
    defaults = {
        "first_name": field("ישראל"),
        "last_name": field("ישראלי"),
        "national_id": field("011223344"),
        "received_date": field("2026-06-18"),
        "sender": field("מכבי"),
        "commitment_number": field("0260005102632"),
    }
    central = fields.pop("central_numbers", [field("048062"), field("948063")])
    issues = fields.pop("issues", [])
    values = RecordFields(**{**defaults, **fields})
    named = [getattr(values, name) for name in RecordFields.model_fields]
    return Record(
        record_id="r1",
        page_id="p1",
        source_file="forms.pdf",
        page_number=3,
        commitment_index=0,
        status="pending",
        version=1,
        form_type="hmo_form",
        fields=values,
        central_numbers=central,
        issues=issues,
        needs_review=any(f.needs_review for f in named + central)
        or any(i.severity != "info" for i in issues),
        created_at=NOW,
        updated_at=NOW,
        approved_at=None,
    )


def rows(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))


def test_csv_starts_with_a_bom_and_the_spec_10_header():
    data = to_csv([])
    assert data.startswith(b"\xef\xbb\xbf")
    assert rows(data) == [HEADER]


def test_a_clean_record_is_one_row_as_text():
    assert rows(to_csv([record()]))[1] == [
        "ישראל",
        "ישראלי",
        "011223344",
        "048062, 948063",  # every central number in one cell
        "18/06/2026",
        "מכבי",
        "0260005102632",  # leading zeros kept
        "",  # nothing to review
        "",
        "forms.pdf",
        "3",
    ]


def test_one_row_per_record():
    assert len(rows(to_csv([record(), record(), record()]))) == 4


def test_a_missing_date_and_items_are_empty_cells():
    row = rows(to_csv([record(received_date=field(None), central_numbers=[field(None)])]))[1]
    assert row[3] == ""
    assert row[4] == ""


def test_review_names_each_flagged_field_and_its_reason():
    flagged = record(
        national_id=field("011223345", issues=["ID_CHECKSUM_INVALID"], needs_review=True),
        commitment_number=field(None, issues=["REQUIRED_MISSING"], needs_review=True),
    )
    assert rows(to_csv([flagged]))[1][7] == (
        "ת״ז: מספר ת״ז לא תקין; מספר התחייבות: לא נמצא בטופס — יש לבדוק"
    )


def test_review_leaves_out_info_and_confirmed_fields():
    flagged = record(
        national_id=field("011223344", issues=["ID_PADDED"]),
        sender=field(None, issues=["REQUIRED_MISSING"], confirmed=True),
        received_date=field(None, issues=["DATE_INVALID"], needs_review=True),
    )
    assert rows(to_csv([flagged]))[1][7] == "תאריך קבלה: תאריך לא תקין"


def test_review_adds_the_record_issues():
    rotated = record(issues=[make_issue("ROTATION_UNRESOLVED")])
    assert rows(to_csv([rotated]))[1][7] == make_issue("ROTATION_UNRESOLVED").message


def test_review_says_a_shared_central_number_reason_once():
    central = [
        field("12345", issues=["CENTRAL_FORMAT"], needs_review=True),
        field("1234567", issues=["CENTRAL_FORMAT"], needs_review=True),
    ]
    assert rows(to_csv([record(central_numbers=central)]))[1][7] == (
        "מספר מרכזי: מספר מרכזי בפורמט חריג"
    )


def test_touched_lists_corrected_and_confirmed_fields_in_column_order():
    touched = record(
        sender=field("מכבי", confirmed=True),
        first_name=field("דנה", corrected=True),
        central_numbers=[field("948062"), field("948064", corrected=True)],
    )
    assert rows(to_csv([touched]))[1][8] == "שם פרטי, מספר מרכזי, גורם שולח"


def test_a_cell_that_looks_like_a_formula_is_quoted():
    hostile = record(first_name=field("=HYPERLINK(1)"), last_name=field("@x"))
    row = rows(to_csv([hostile]))[1]
    assert row[0] == "'=HYPERLINK(1)"
    assert row[1] == "'@x"


def test_json_is_the_list_of_records():
    data = json.loads(to_json([record()]).decode("utf-8"))
    assert [Record.model_validate(item) for item in data] == [record()]
    assert data[0]["fields"]["national_id"]["value"] == "011223344"


def test_filename_has_the_date_and_format():
    assert export_filename("csv", date(2026, 10, 19)) == "records-2026-10-19.csv"
    assert export_filename("json", date(2026, 10, 19)) == "records-2026-10-19.json"
