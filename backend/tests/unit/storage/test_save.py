"""save_extracted_page against a real Postgres (Dev-B plan B1.3, A2 in #15)."""

import asyncio
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.extraction.provider import PageImage
from app.rules.engine import apply_rules
from app.schemas.api import Form, User
from app.storage import repo
from app.storage.service import save_extracted_page

FIXTURES = Path(__file__).parents[2] / "fixtures" / "rules"
TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
USER = User(id="u1", username="tester", display_name="Tester")


def make_form(name="clean", *, file_id="f1", page_number=1, continuation_pages=(), **update):
    form = Form.model_validate_json((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    form = form.model_copy(
        update={
            "file_id": file_id,
            "page_number": page_number,
            "continuation_pages": list(continuation_pages),
            "form_type": "hmo_form",
            **update,
        }
    )
    return apply_rules(form, today=TODAY)


def images_for(form, file_id=None):
    return [
        PageImage(
            file_id=file_id or form.file_id,
            filename=form.source_file,
            page_number=number,
            rotation=90,
            jpeg=f"jpeg-{number}".encode(),
        )
        for number in [form.page_number, *form.continuation_pages]
    ]


@pytest.fixture
def user(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES (%s, %s, 'x', %s, %s)",
            (USER.id, USER.username, USER.display_name, NOW),
        )
    return USER


def save(db, form, images=None, user=USER):
    async def go():
        async with await db.connect_async() as conn:
            return await save_extracted_page(
                conn, form, images_for(form) if images is None else images, user, now=NOW
            )

    return db.run(go())


def rows(db, sql, params=()):
    with db.connect() as conn:
        return conn.execute(sql, params).fetchall()


def test_saves_one_record_per_commitment_with_the_form_values(db, user):
    form = make_form("multi_values")

    records = save(db, form)

    assert [r.commitment_index for r in records] == [0, 1]
    assert {r.page_id for r in records} == {records[0].page_id}
    assert all(r.status == "pending" and r.version == 1 for r in records)
    assert all(r.form_type == "hmo_form" for r in records)
    assert [r.fields.commitment_number.value for r in records] == [
        c.value for c in form.commitment_numbers
    ]


def test_returned_records_match_what_is_stored(db, user):
    form = make_form("multi_values")

    records = save(db, form)

    stored = rows(db, "SELECT * FROM record ORDER BY commitment_idx")
    for record, row in zip(records, stored, strict=True):
        assert row["id"] == record.record_id
        assert row["fields"] == record.fields.model_dump(mode="json")
        assert row["central_numbers"] == [c.model_dump(mode="json") for c in record.central_numbers]
        assert row["issues"] == [i.model_dump(mode="json") for i in record.issues]
        assert row["needs_review"] == record.needs_review
        assert row["created_by"] == "u1"


def test_effective_columns_for_search_and_filters(db, user):
    form = make_form("clean")

    [record] = save(db, form)

    [row] = rows(db, "SELECT * FROM record")
    fields = record.fields
    assert row["national_id"] == fields.national_id.value
    assert row["commitment_number"] == fields.commitment_number.value
    assert row["central_values"] == [c.value for c in record.central_numbers]
    assert row["received_date"] == date.fromisoformat(fields.received_date.value)
    assert row["sender"] == fields.sender.value
    assert fields.national_id.value in row["search_text"]
    assert fields.commitment_number.value in row["search_text"]


def test_leading_zeros_survive(db, user):
    form = make_form("clean")
    national_id = form.fields.national_id.model_copy(update={"value": "000000018"})
    form = form.model_copy(
        update={"fields": form.fields.model_copy(update={"national_id": national_id})}
    )

    [record] = save(db, form)

    [row] = rows(db, "SELECT national_id, fields FROM record")
    assert record.fields.national_id.value == "000000018"
    assert row["national_id"] == "000000018"
    assert row["fields"]["national_id"]["value"] == "000000018"


def test_invalid_date_is_kept_in_fields_but_not_in_the_date_column(db, user):
    form = make_form("clean")
    bad = form.fields.received_date.model_copy(update={"value": "31/02/26"})
    form = form.model_copy(update={"fields": form.fields.model_copy(update={"received_date": bad})})

    save(db, form)

    [row] = rows(db, "SELECT received_date, fields FROM record")
    assert row["received_date"] is None
    assert row["fields"]["received_date"]["value"] == "31/02/26"


def test_saves_every_page_of_the_form_with_its_image(db, user):
    form = make_form("clean", page_number=3, continuation_pages=[4, 5])

    [record] = save(db, form)

    pages = rows(
        db,
        "SELECT p.*, i.mime, i.sha256, i.bytes FROM page p"
        " JOIN page_image i ON i.page_id = p.id ORDER BY p.page_number",
    )
    assert [p["page_number"] for p in pages] == [3, 4, 5]
    assert pages[0]["id"] == record.page_id
    assert pages[0]["first_page_id"] is None
    assert [p["first_page_id"] for p in pages[1:]] == [record.page_id] * 2
    assert [p["id"] for p in pages[1:]] == record.continuation_page_ids
    assert record.continuation_pages == [4, 5]
    assert all(p["file_id"] == "f1" and p["rotation"] == 90 for p in pages)
    assert [bytes(p["bytes"]) for p in pages] == [b"jpeg-3", b"jpeg-4", b"jpeg-5"]
    assert pages[0]["sha256"] == hashlib.sha256(b"jpeg-3").hexdigest()
    assert {p["mime"] for p in pages} == {"image/jpeg"}


def test_a_one_page_form_has_no_continuation_page_ids(db, user):
    [record] = save(db, make_form("clean"))

    assert record.continuation_page_ids == []


def test_writes_a_created_event_per_record_without_values(db, user):
    records = save(db, make_form("multi_values"))

    events = rows(db, "SELECT record_id, user_id, action, field FROM record_event ORDER BY id")
    assert events == [
        {"record_id": r.record_id, "user_id": "u1", "action": "created", "field": None}
        for r in records
    ]


@pytest.mark.parametrize(
    "images",
    [
        pytest.param(lambda form: images_for(form)[:1], id="continuation page missing"),
        pytest.param(lambda form: images_for(form)[::-1], id="wrong order"),
        pytest.param(lambda form: images_for(form, file_id="other"), id="another file"),
    ],
)
def test_wrong_images_raise_and_save_nothing(db, user, images):
    form = make_form("clean", continuation_pages=[2])

    with pytest.raises(ValueError, match=form.form_id):
        save(db, form, images(form))

    assert rows(db, "SELECT COUNT(*) AS n FROM page") == [{"n": 0}]


def test_failed_extraction_is_never_saved(db, user):
    form = make_form("clean").model_copy(update={"processing_status": "error"})

    with pytest.raises(ValueError, match="A7"):
        save(db, form)

    assert rows(db, "SELECT COUNT(*) AS n FROM page") == [{"n": 0}]


def test_a_failure_midway_saves_nothing(db, user, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(repo, "insert_event", broken)

    with pytest.raises(RuntimeError):
        save(db, make_form("clean", continuation_pages=[2]))

    for table in ("page", "page_image", "record", "record_event"):
        assert rows(db, f"SELECT COUNT(*) AS n FROM {table}") == [{"n": 0}]


def test_commitment_already_saved_is_flagged_duplicate(db, user):
    [first] = save(db, make_form("clean", file_id="f1"))

    [second] = save(db, make_form("clean", file_id="f2"))

    field = second.fields.commitment_number
    assert [i.code for i in field.issues][-1] == "DUPLICATE_RECORD"
    assert field.needs_review and second.needs_review
    assert "DUPLICATE_RECORD" not in [i.code for i in first.fields.commitment_number.issues]
    [stored] = rows(db, "SELECT needs_review FROM record WHERE id = %s", (second.record_id,))
    assert stored["needs_review"] is True


def test_two_saves_at_once_with_the_same_commitment_flag_exactly_one(db, user):
    async def both():
        async def one(file_id):
            async with await db.connect_async() as conn:
                form = make_form("clean", file_id=file_id)
                return await save_extracted_page(conn, form, images_for(form), USER, now=NOW)

        return await asyncio.gather(one("f1"), one("f2"))

    results = db.run(both())

    flagged = [
        "DUPLICATE_RECORD" in [i.code for i in record.fields.commitment_number.issues]
        for [record] in results
    ]
    assert sorted(flagged) == [False, True]
