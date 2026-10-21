"""form_type (D17) and continuation_pages (A1) in the contract, from issue #15.

Owner: shared
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from app.schemas import api, extraction

CLEAN_FORM = Path(__file__).parents[1] / "fixtures" / "rules" / "clean.json"
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)


def form_data() -> dict:
    return json.loads(CLEAN_FORM.read_text(encoding="utf-8"))


def record_data(**overrides) -> dict:
    form = api.Form.model_validate(form_data())
    data = {
        "record_id": "r1",
        "page_id": "p1",
        "source_file": form.source_file,
        "page_number": form.page_number,
        "commitment_index": 0,
        "status": "pending",
        "version": 1,
        "form_type": "hmo_form",
        "fields": {**form.fields.model_dump(), "commitment_number": form.commitment_numbers[0]},
        "central_numbers": form.central_numbers,
        "issues": [],
        "needs_review": False,
        "created_at": NOW,
        "updated_at": NOW,
        "approved_at": None,
    }
    return {**data, **overrides}


def summary_data(**overrides) -> dict:
    data = {
        "record_id": "r1",
        "page_id": "p1",
        "source_file": "a.pdf",
        "page_number": 1,
        "commitment_index": 0,
        "status": "pending",
        "needs_review": False,
        "first_name": None,
        "last_name": None,
        "national_id": None,
        "commitment_number": None,
        "central_numbers": [],
        "sender": None,
        "form_type": "lab_report",
        "received_date": None,
        "created_at": NOW,
        "approved_at": None,
    }
    return {**data, **overrides}


def test_contract_form_types_match_what_the_model_returns():
    assert get_args(api.FormType) == get_args(extraction.FormType)


def test_form_type_defaults_to_unknown_until_assemble_passes_it():
    assert api.Form.model_validate(form_data()).form_type == "unknown"


def test_form_keeps_its_form_type():
    form = api.Form.model_validate({**form_data(), "form_type": "hospital_form"})
    assert form.form_type == "hospital_form"


def test_record_requires_form_type():
    data = record_data()
    del data["form_type"]
    with pytest.raises(ValidationError, match="form_type"):
        api.Record.model_validate(data)


@pytest.mark.parametrize(
    "model, data", [(api.Record, record_data), (api.RecordSummary, summary_data)]
)
def test_unknown_form_type_value_is_rejected(model, data):
    with pytest.raises(ValidationError, match="form_type"):
        model.model_validate(data(form_type="clalit"))


def test_record_summary_requires_form_type():
    data = summary_data()
    del data["form_type"]
    with pytest.raises(ValidationError, match="form_type"):
        api.RecordSummary.model_validate(data)


def test_form_is_a_single_page_by_default():
    assert api.Form.model_validate(form_data()).continuation_pages == []


def test_form_keeps_its_continuation_pages():
    form = api.Form.model_validate({**form_data(), "continuation_pages": [4, 5]})
    assert (form.page_number, form.continuation_pages) == (1, [4, 5])


def test_record_continuation_pages_default_to_empty():
    assert api.Record.model_validate(record_data()).continuation_pages == []
    assert api.Record.model_validate(record_data(continuation_pages=[2])).continuation_pages == [2]


def test_record_has_no_user_fields():
    # No sign-in (21.10): a record says when it was approved, not by whom.
    assert {"approved_by", "updated_by"}.isdisjoint(api.Record.model_fields)


def test_record_list_requires_counts():
    data = {"items": [summary_data()], "total": 1, "limit": 50, "offset": 0}
    with pytest.raises(ValidationError, match="counts"):
        api.RecordList.model_validate(data)

    counts = {"pending": 1, "approved": 0, "needs_review": 0}
    assert api.RecordList.model_validate({**data, "counts": counts}).counts.pending == 1


def test_bulk_approve_response_lists_approved_and_skipped_records():
    response = api.BulkApproveResponse.model_validate(
        {
            "approved": [record_data(status="approved", approved_at=NOW)],
            "skipped": [
                {
                    "record_id": "r2",
                    "type": "review_required",
                    "blocking_fields": ["national_id", "central_numbers[1]"],
                },
                {"record_id": "r3", "type": "version_conflict"},
            ],
        }
    )
    assert [r.record_id for r in response.approved] == ["r1"]
    assert [(s.record_id, s.blocking_fields) for s in response.skipped] == [
        ("r2", ["national_id", "central_numbers[1]"]),
        ("r3", None),
    ]


def test_skipped_record_needs_a_known_reason():
    with pytest.raises(ValidationError, match="type"):
        api.SkippedRecord.model_validate({"record_id": "r1", "type": "oops"})
