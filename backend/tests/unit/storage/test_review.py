"""Records after saving: read, list, patch, approve, delete, against a real Postgres
(Dev-B plan B1.2, B1.3)."""

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import get_args

import pytest

from app.extraction.provider import PageImage
from app.rules.engine import apply_rules
from app.schemas.api import (
    ApproveRequest,
    BulkApproveItem,
    Form,
    RecordPatch,
    RecordSort,
    User,
)
from app.storage import repo, review
from app.storage.review import RecordProblem
from app.storage.service import save_extracted_page

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"
TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
USER = User(id="u1", username="dana", display_name="דנה")


@pytest.fixture(autouse=True)
def user(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES (%s, %s, 'x', %s, %s)",
            (USER.id, USER.username, USER.display_name, NOW),
        )


def save(db, name="clean", *, file_id="f1", now=NOW, **update):
    form = Form.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    form = apply_rules(
        form.model_copy(update={"file_id": file_id, "form_type": "hmo_form", **update}),
        today=TODAY,
    )
    images = [
        PageImage(
            file_id=file_id,
            filename=form.source_file,
            page_number=number,
            rotation=0,
            jpeg=b"jpeg",
        )
        for number in [form.page_number, *form.continuation_pages]
    ]

    async def go():
        async with await db.connect_async() as conn:
            return await save_extracted_page(conn, form, images, USER, now=now)

    return db.run(go())


def call(db, fn, *args, **kwargs):
    async def go():
        async with await db.connect_async() as conn:
            return await fn(conn, *args, **kwargs)

    return db.run(go())


def patch(db, record, **body):
    body = RecordPatch.model_validate({"version": record.version, **body})
    return call(db, review.patch_record, record.record_id, body, USER, today=TODAY, now=NOW)


def approve(db, record):
    body = ApproveRequest(version=record.version)
    return call(db, review.approve_record, record.record_id, body, USER, today=TODAY, now=NOW)


def problem(db, fn, *args, **kwargs) -> RecordProblem:
    with pytest.raises(RecordProblem) as exc:
        if fn in (patch, approve):
            fn(db, *args, **kwargs)
        else:
            call(db, fn, *args, **kwargs)
    return exc.value


# --- Reading


def test_get_returns_the_saved_record(db):
    [saved] = save(db)
    assert call(db, review.get_record, saved.record_id) == saved


def test_get_an_unknown_record_is_not_found(db):
    assert problem(db, review.get_record, "nope").type == "not_found"


def test_list_is_newest_first_with_counts(db):
    save(db, "clean", file_id="f1", now=NOW)
    save(db, "multi_values", file_id="f2", now=NOW + timedelta(minutes=1))
    page = call(db, review.list_records)

    assert [r.commitment_index for r in page.items] == [0, 1, 0]
    assert page.items[0].central_numbers == ["948062", "948063"]
    assert page.total == 3
    assert page.counts.model_dump() == {"pending": 3, "approved": 0, "needs_review": 0}


def test_list_searches_partial_numbers_and_names(db):
    save(db, "clean", file_id="f1")
    save(db, "no_commitment", file_id="f2")
    first_name = call(db, review.list_records).items[0].first_name

    assert call(db, review.list_records, q="1223").total == 2  # part of the national ID
    assert call(db, review.list_records, q="2600051026").total == 1  # part of a commitment
    assert call(db, review.list_records, q="948070").total == 1  # a central number
    assert call(db, review.list_records, q=f" {first_name[:2]} ").total == 2


def test_like_takes_wildcards_literally():
    # fold_text drops % and _ from a search, but the pattern must not depend on it.
    assert repo._like("5%_\\") == r"%5\%\_\\%"


def test_list_filters_combine_and_counts_ignore_status(db):
    save(db, "clean", file_id="f1")
    save(db, "no_commitment", file_id="f2")

    flagged = call(db, review.list_records, needs_review=True)
    assert flagged.total == 1
    assert flagged.items[0].commitment_number is None
    assert call(db, review.list_records, date_from=date(2026, 6, 17)).total == 1
    assert call(db, review.list_records, form_type="lab_report").total == 0

    approved = call(db, review.list_records, status="approved")
    assert approved.total == 0
    assert approved.counts.model_dump() == {"pending": 2, "approved": 0, "needs_review": 1}


def test_list_pages_keep_the_total(db):
    save(db, "multi_values")
    page = call(db, review.list_records, limit=1, offset=5)
    assert (page.items, page.total) == ([], 2)


def test_list_sorts_by_a_column_with_empty_values_last(db):
    save(db, "clean", file_id="f1", now=NOW)
    save(db, "multi_values", file_id="f2", now=NOW + timedelta(minutes=1))
    save(db, "no_commitment", file_id="f3", now=NOW + timedelta(minutes=2))

    def numbers(sort):
        return [r.commitment_number for r in call(db, review.list_records, sort=sort).items]

    ascending, descending = numbers("commitment_number"), numbers("-commitment_number")
    present = [n for n in ascending if n is not None]
    assert present == sorted(present)
    assert ascending[-1] is None and descending[-1] is None  # empty last, either way
    assert [n for n in descending if n is not None] == sorted(present, reverse=True)


def test_list_sort_ties_keep_the_default_order_so_pages_are_stable(db):
    save(db, "clean", file_id="f1", now=NOW)
    save(db, "multi_values", file_id="f2", now=NOW + timedelta(minutes=1))
    everything = [r.record_id for r in call(db, review.list_records, sort="form_type").items]
    pages = [
        r.record_id
        for offset in range(len(everything))
        for r in call(db, review.list_records, sort="form_type", limit=1, offset=offset).items
    ]
    assert pages == everything
    # Every record has the same form type, so the default order (newest first) decides.
    assert everything == [r.record_id for r in call(db, review.list_records).items]


def test_every_sort_key_runs(db):
    save(db, "clean")
    for sort in get_args(RecordSort):
        assert call(db, review.list_records, sort=sort).total == 1


# --- Patch


def test_a_correction_reruns_the_rules_and_keeps_raw(db):
    [record] = save(db, "unclear")
    response = patch(db, record, fields={"national_id": {"value": "11223344"}})

    field = response.record.fields.national_id
    assert field.value == "011223344"  # normalized from what was typed
    assert field.raw == record.fields.national_id.raw
    assert (field.corrected, field.confirmed, field.needs_review) == (True, False, False)
    assert response.record.version == record.version + 1
    assert response.record.updated_by == "דנה"
    assert response.siblings == []  # one record in this form


def test_confirming_a_field_clears_its_flag_but_keeps_the_issue(db):
    [record] = save(db, "unclear")
    response = patch(db, record, fields={"first_name": {"confirmed": True}})

    field = response.record.fields.first_name
    assert field.confirmed and not field.needs_review
    assert [i.code for i in field.issues] == ["FIELD_UNCLEAR"]


def test_a_shared_field_changes_in_every_record_of_the_form(db):
    first, second = save(db, "multi_values")
    response = patch(db, first, fields={"last_name": {"value": "כהן"}})

    [sibling] = response.siblings
    assert sibling.record_id == second.record_id
    assert sibling.fields.last_name.value == "כהן"
    assert sibling.version == second.version + 1
    assert call(db, review.get_record, second.record_id) == sibling


def test_a_commitment_number_is_the_records_own(db):
    first, second = save(db, "multi_values")
    response = patch(db, first, fields={"commitment_number": {"value": "999999"}})

    assert response.siblings == []
    assert call(db, review.get_record, second.record_id) == second


def test_a_shared_field_is_refused_when_a_sibling_is_approved(db):
    first, second = save(db, "multi_values")
    approve(db, second)

    assert (
        problem(db, patch, first, fields={"sender": {"value": "מכבי"}}).type == "sibling_approved"
    )
    # Its own commitment number is still free to change.
    patch(db, first, fields={"commitment_number": {"value": "999999"}})


def test_a_stale_version_or_an_approved_record_is_refused(db):
    [record] = save(db)
    patch(db, record, fields={"first_name": {"value": "רות"}})

    assert problem(db, patch, record, fields={"last_name": {"value": "x"}}).type == (
        "version_conflict"
    )
    approve(db, call(db, review.get_record, record.record_id))
    fresh = call(db, review.get_record, record.record_id)
    assert problem(db, patch, fresh, fields={"last_name": {"value": "x"}}).type == (
        "record_approved"
    )


def test_central_numbers_are_replaced_as_a_list(db):
    [record] = save(db, "multi_values", file_id="f1")[:1]
    response = patch(db, record, central_numbers=[{"idx": 1}, {"value": "123456"}])

    central = response.record.central_numbers
    assert [c.value for c in central] == ["948063", "123456"]
    assert central[0].raw == record.central_numbers[1].raw
    assert central[1].corrected
    assert problem(db, patch, response.record, central_numbers=[{"idx": 7}]).status == 422


def test_a_patch_logs_who_changed_which_field_without_values(db):
    [record] = save(db)
    patch(db, record, fields={"sender": {"value": "מכבי"}, "first_name": {"confirmed": True}})

    with db.connect() as conn:
        events = conn.execute(
            "SELECT action, field, user_id FROM record_event WHERE record_id = %s"
            " AND action <> 'created' ORDER BY field",
            (record.record_id,),
        ).fetchall()
    assert events == [
        {"action": "confirmed", "field": "first_name", "user_id": "u1"},
        {"action": "corrected", "field": "sender", "user_id": "u1"},
    ]


# --- Duplicates (A4)


def test_a_duplicate_stays_flagged_across_edits_until_confirmed(db):
    save(db, "clean", file_id="f1")
    [duplicate] = save(db, "clean", file_id="f2")
    assert duplicate.fields.commitment_number.needs_review

    edited = patch(db, duplicate, fields={"first_name": {"value": "רות"}}).record
    codes = [i.code for i in edited.fields.commitment_number.issues]
    assert "DUPLICATE_RECORD" in codes and edited.needs_review

    confirmed = patch(db, edited, fields={"commitment_number": {"confirmed": True}}).record
    assert not confirmed.fields.commitment_number.needs_review


def test_the_flag_goes_once_the_other_record_is_deleted(db):
    [first] = save(db, "clean", file_id="f1")
    [duplicate] = save(db, "clean", file_id="f2")
    call(db, review.delete_record, first.record_id)

    approved = approve(db, duplicate)
    assert approved.status == "approved"
    assert not approved.fields.commitment_number.issues


def test_the_record_saved_first_is_not_flagged_by_a_later_copy(db):
    [first] = save(db, "clean", file_id="f1")
    save(db, "clean", file_id="f2")

    edited = patch(db, first, fields={"first_name": {"value": "רות"}}).record
    assert not edited.fields.commitment_number.issues
    assert approve(db, edited).status == "approved"


def test_changing_only_the_number_to_one_another_record_has_does_not_flag(db):
    [taken] = save(db, "clean", file_id="f1")  # central 948062
    [record] = save(db, "no_commitment", file_id="f2")  # central 948070
    number = taken.fields.commitment_number.value

    edited = patch(db, record, fields={"commitment_number": {"value": number}}).record
    assert not edited.fields.commitment_number.issues


def test_changing_the_central_numbers_to_match_flags_it(db):
    [taken] = save(db, "clean", file_id="f1")
    [record] = save(db, "no_commitment", file_id="f2")
    number = taken.fields.commitment_number.value
    record = patch(db, record, fields={"commitment_number": {"value": number}}).record

    edited = patch(db, record, central_numbers=[{"idx": 0, "value": "948062"}]).record

    [issue] = edited.fields.commitment_number.issues
    assert issue.code == "DUPLICATE_RECORD"
    assert [d.record_id for d in issue.duplicate_of] == [taken.record_id]
    assert edited.needs_review


def test_changing_the_central_numbers_away_clears_the_flag(db):
    save(db, "clean", file_id="f1")
    [duplicate] = save(db, "clean", file_id="f2")

    edited = patch(db, duplicate, central_numbers=[{"idx": 0, "value": "948070"}]).record

    assert not edited.fields.commitment_number.issues
    assert approve(db, edited).status == "approved"


def test_every_earlier_copy_is_named_oldest_first(db):
    later = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
    [first] = save(db, "clean", file_id="f1", now=later)
    [older] = save(db, "clean", file_id="f2", now=NOW)
    [record] = save(db, "clean", file_id="f3")

    [issue] = record.fields.commitment_number.issues
    assert [(d.record_id, d.created_at, d.created_by) for d in issue.duplicate_of] == [
        (older.record_id, NOW, "דנה"),
        (first.record_id, later, "דנה"),
    ]


# --- Approve


def test_approve_is_blocked_while_a_field_needs_review(db):
    [record] = save(db, "no_commitment")
    blocked = problem(db, approve, record)

    assert (blocked.status, blocked.type) == (409, "review_required")
    assert blocked.blocking_fields == ["commitment_number"]


def test_approve_after_confirming_the_empty_field(db):
    [record] = save(db, "no_commitment")
    confirmed = patch(db, record, fields={"commitment_number": {"confirmed": True}}).record
    approved = approve(db, confirmed)

    assert approved.status == "approved"
    assert (approved.approved_by, approved.approved_at) == ("דנה", NOW)


def test_approve_many_approves_the_ready_and_skips_the_rest(db):
    [ready] = save(db, "clean", file_id="f1")
    [flagged] = save(db, "no_commitment", file_id="f2")
    items = [
        BulkApproveItem(record_id=ready.record_id, version=ready.version),
        BulkApproveItem(record_id=flagged.record_id, version=flagged.version),
        BulkApproveItem(record_id="nope", version=1),
    ]
    result = call(db, review.approve_many, items, USER, today=TODAY, now=NOW)

    assert [r.record_id for r in result.approved] == [ready.record_id]
    assert [(s.record_id, s.type) for s in result.skipped] == [
        (flagged.record_id, "review_required"),
        ("nope", "not_found"),
    ]
    assert result.skipped[0].blocking_fields == ["commitment_number"]


# --- Delete


def test_deleting_the_forms_last_record_deletes_its_pages(db):
    first, second = save(db, "multi_values")
    call(db, review.delete_record, first.record_id)
    assert call(db, repo.get_page_image, first.page_id) == b"jpeg"

    call(db, review.delete_record, second.record_id)
    assert call(db, repo.get_page_image, first.page_id) is None
    assert problem(db, review.get_record, second.record_id).type == "not_found"


def test_an_approved_record_is_not_deleted(db):
    [record] = save(db)
    approve(db, record)
    assert problem(db, review.delete_record, record.record_id).type == "record_approved"


# --- Export


def export(db, export_format="csv", **filters):
    return call(db, review.export_records, USER, export_format=export_format, now=NOW, **filters)


def export_log(db):
    with db.connect() as conn:
        return conn.execute("SELECT user_id, format, record_count FROM export_log").fetchall()


def test_export_has_the_full_records_of_the_list_without_paging(db):
    save(db, "clean", file_id="f1", now=NOW)
    save(db, "multi_values", file_id="f2", now=NOW + timedelta(minutes=1))
    listed = call(db, review.list_records, limit=1)

    exported = export(db)
    assert [r.record_id for r in exported][:1] == [listed.items[0].record_id]  # same order
    assert len(exported) == listed.total == 3
    assert exported[0] == call(db, review.get_record, exported[0].record_id)


def test_export_takes_the_list_filters_and_no_status_means_every_record(db):
    [ready] = save(db, "clean", file_id="f1")
    save(db, "no_commitment", file_id="f2")
    approve(db, ready)

    assert len(export(db)) == 2
    assert [r.record_id for r in export(db, status="approved")] == [ready.record_id]
    assert len(export(db, status="pending", needs_review=True)) == 1
    assert len(export(db, q="948070")) == 1
    assert export(db, form_type="lab_report") == []


def test_export_is_in_the_lists_sort_order(db):
    save(db, "clean", file_id="f1", now=NOW)
    save(db, "multi_values", file_id="f2", now=NOW + timedelta(minutes=1))
    save(db, "no_commitment", file_id="f3", now=NOW + timedelta(minutes=2))

    listed = [r.record_id for r in call(db, review.list_records, sort="commitment_number").items]
    assert [r.record_id for r in export(db, sort="commitment_number")] == listed


def test_every_export_is_logged_without_values(db):
    save(db, "multi_values")
    export(db, "csv")
    export(db, "json", status="approved")

    assert export_log(db) == [
        {"user_id": USER.id, "format": "csv", "record_count": 2},
        {"user_id": USER.id, "format": "json", "record_count": 0},
    ]


def test_too_many_records_is_refused_and_not_logged(db, monkeypatch):
    monkeypatch.setattr(review, "MAX_EXPORT", 1)
    save(db, "multi_values")

    refused = problem(db, review.export_records, USER, export_format="csv", now=NOW)
    assert (refused.status, refused.type) == (422, "export_too_large")
    assert export_log(db) == []
