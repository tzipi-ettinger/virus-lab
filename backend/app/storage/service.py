"""Records logic above repo.py: save an extracted form (Dev-B plan 2.5).

Owner: B
"""

from datetime import UTC, date, datetime
from uuid import uuid4

from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

from app.extraction.provider import PageImage
from app.pipeline.service import ExtractedForm, SaveForm
from app.rules.issues import make_issue
from app.rules.records import RecordDraft, build_records
from app.rules.text import fold_text
from app.schemas.api import Form, Record
from app.storage import repo


async def save_extracted_page(
    conn: AsyncConnection,
    form: Form,
    images: list[PageImage],
    *,
    now: datetime | None = None,
) -> list[Record]:
    """Save one form: its pages, their images and its records, in one transaction.

    `form` comes from the pipeline after apply_rules, so the rules don't run again.
    `images` are the pages to keep for the preview: the first page, then each of
    form.continuation_pages in order, all from one file. A wrong list, or a form
    whose extraction failed (A7), is a bug in the caller and not in the upload:
    ValueError, and nothing is saved. If anything fails, nothing of the form is saved.

    A commitment number that another record already has is flagged
    DUPLICATE_RECORD (A4). The form's numbers are locked first, so two uploads
    saving the same number at once can't both miss each other.
    """
    _check_images(form, images)
    now = now or datetime.now(UTC)
    drafts = build_records(form)
    numbers = [n for draft in drafts if (n := draft.fields.commitment_number.value)]
    page_ids = [str(uuid4()) for _ in images]
    first_page_id = page_ids[0]

    async with conn.transaction():
        await repo.lock_commitments(conn, numbers)
        existing = await repo.existing_commitments(conn, numbers)
        for page_id, image in zip(page_ids, images, strict=True):
            await repo.insert_page(
                conn,
                page_id=page_id,
                file_id=image.file_id,
                source_filename=form.source_file,
                page_number=image.page_number,
                rotation=image.rotation,
                first_page_id=None if page_id == first_page_id else first_page_id,
                now=now,
            )
            await repo.insert_page_image(conn, page_id, image.jpeg)

        records = []
        for draft in drafts:
            if draft.fields.commitment_number.value in existing:
                draft = _flag_duplicate(draft)
            record = _to_record(draft, form, first_page_id, page_ids[1:], now)
            await _insert(conn, record)
            records.append(record)
    return records


def form_saver(pool: AsyncConnectionPool) -> SaveForm:
    """The pipeline's SaveForm for one request: each form on its own short
    connection from the pool, so a long upload never holds one."""

    async def save(extracted: ExtractedForm) -> list[Record]:
        async with pool.connection() as conn:
            return await save_extracted_page(conn, extracted.form, extracted.images)

    return save


def _check_images(form: Form, images: list[PageImage]) -> None:
    if form.processing_status != "ok":
        raise ValueError(f"form {form.form_id}: a failed extraction is never saved (A7)")
    expected = [form.page_number, *form.continuation_pages]
    got = [image.page_number for image in images]
    if got != expected:
        raise ValueError(f"form {form.form_id}: images for pages {got}, expected {expected}")
    if {image.file_id for image in images} != {form.file_id}:
        raise ValueError(f"form {form.form_id}: every image must come from file {form.file_id}")


def _flag_duplicate(draft: RecordDraft) -> RecordDraft:
    field = draft.fields.commitment_number
    flagged = field.model_copy(
        update={
            "issues": [*field.issues, make_issue("DUPLICATE_RECORD")],
            "needs_review": not field.confirmed,
        }
    )
    return draft.model_copy(
        update={
            "fields": draft.fields.model_copy(update={"commitment_number": flagged}),
            "needs_review": draft.needs_review or flagged.needs_review,
        }
    )


def _to_record(
    draft: RecordDraft, form: Form, page_id: str, continuation_page_ids: list[str], now: datetime
) -> Record:
    return Record(
        record_id=str(uuid4()),
        page_id=page_id,
        source_file=form.source_file,
        page_number=form.page_number,
        continuation_pages=form.continuation_pages,
        continuation_page_ids=continuation_page_ids,
        commitment_index=draft.commitment_index,
        status="pending",
        version=1,
        form_type=form.form_type,
        fields=draft.fields,
        central_numbers=draft.central_numbers,
        issues=draft.issues,
        needs_review=draft.needs_review,
        created_at=now,
        updated_at=now,
        approved_at=None,
    )


async def _insert(conn: AsyncConnection, record: Record) -> None:
    fields = record.fields
    central_values = [item.value for item in record.central_numbers if item.value]
    await repo.insert_record(
        conn,
        record_id=record.record_id,
        page_id=record.page_id,
        commitment_idx=record.commitment_index,
        needs_review=record.needs_review,
        form_type=record.form_type,
        fields=fields.model_dump(mode="json"),
        central_numbers=[item.model_dump(mode="json") for item in record.central_numbers],
        issues=[issue.model_dump(mode="json") for issue in record.issues],
        national_id=fields.national_id.value,
        commitment_number=fields.commitment_number.value,
        central_values=central_values,
        first_name=fields.first_name.value,
        last_name=fields.last_name.value,
        sender=fields.sender.value,
        received_date=_iso_date(fields.received_date.value),
        search_text=search_text(record),
        now=record.created_at,
    )
    await repo.insert_event(
        conn, record_id=record.record_id, action="created", now=record.created_at
    )


def search_text(record: Record) -> str:
    """What the records search matches: names, IDs, numbers and sender, folded (Dev-B plan 2.5)."""
    fields = record.fields
    values = [
        fields.first_name.value,
        fields.last_name.value,
        fields.national_id.value,
        fields.commitment_number.value,
        fields.sender.value,
        *(item.value for item in record.central_numbers),
    ]
    return fold_text(" ".join(value for value in values if value))


def _iso_date(value: str | None) -> date | None:
    """The date column holds only a valid date; an invalid one stays in `fields` for review."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
