"""Records after they are saved: read, list, patch, approve and delete (Dev-B plan 2.5).

The rules run again on every patch and approve (SPEC 7.4): from what the user typed
for a corrected field, from raw otherwise, and never from issues the client sent.
Each change runs in one transaction that holds the record's row lock, so two tabs
can't both save over the same version.

Owner: B
"""

from collections.abc import Iterable
from datetime import date, datetime

from psycopg import AsyncConnection

from app.rules.engine import apply_rules
from app.rules.issues import make_issue
from app.rules.records import blocking_fields
from app.rules.review_policy import is_blocking
from app.rules.text import fold_text
from app.schemas.api import (
    ApproveRequest,
    BulkApproveItem,
    BulkApproveResponse,
    FieldEdit,
    Form,
    FormField,
    FormFields,
    Issue,
    ListItemEdit,
    Record,
    RecordCounts,
    RecordFields,
    RecordList,
    RecordPatch,
    RecordPatchResponse,
    RecordSummary,
    SkippedRecord,
    User,
)
from app.storage import repo
from app.storage.service import _iso_date, search_text

# The fields every record of a form shares (A3). commitment_number is the record's own.
SHARED = tuple(FormFields.model_fields)


class RecordProblem(Exception):
    """Why a record can't be read or changed. The API turns it into a Problem."""

    def __init__(
        self, status: int, type_: str, title: str, blocking_fields: list[str] | None = None
    ) -> None:
        super().__init__(title)
        self.status = status
        self.type = type_
        self.title = title
        self.blocking_fields = blocking_fields


def _not_found() -> RecordProblem:
    return RecordProblem(404, "not_found", "הרשומה לא נמצאה")


# --- Rows to contract models


def to_record(row: dict) -> Record:
    return Record(
        record_id=row["id"],
        page_id=row["page_id"],
        source_file=row["source_filename"],
        page_number=row["page_number"],
        continuation_pages=row["continuation_pages"],
        continuation_page_ids=row["continuation_page_ids"],
        commitment_index=row["commitment_idx"],
        status=row["status"],
        version=row["version"],
        form_type=row["form_type"],
        fields=RecordFields.model_validate(row["fields"]),
        central_numbers=[FormField.model_validate(item) for item in row["central_numbers"]],
        issues=[Issue.model_validate(issue) for issue in row["issues"]],
        needs_review=row["needs_review"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        approved_at=row["approved_at"],
        approved_by=row["approved_by_username"],
        updated_by=row["updated_by_username"],
    )


def _to_summary(row: dict) -> RecordSummary:
    received = row["received_date"]
    return RecordSummary(
        record_id=row["id"],
        page_id=row["page_id"],
        source_file=row["source_filename"],
        page_number=row["page_number"],
        commitment_index=row["commitment_idx"],
        status=row["status"],
        needs_review=row["needs_review"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        national_id=row["national_id"],
        commitment_number=row["commitment_number"],
        central_numbers=row["central_values"],
        sender=row["sender"],
        form_type=row["form_type"],
        received_date=received.isoformat() if received else None,
        created_at=row["created_at"],
        approved_at=row["approved_at"],
    )


# --- Reading


async def get_record(conn: AsyncConnection, record_id: str) -> Record:
    async with conn.transaction():
        row = await repo.get_record(conn, record_id)
    if row is None:
        raise _not_found()
    return to_record(row)


async def list_records(
    conn: AsyncConnection,
    *,
    q: str | None = None,
    status: str | None = None,
    needs_review: bool | None = None,
    sender: str | None = None,
    form_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "-created_at",
    limit: int = 50,
    offset: int = 0,
) -> RecordList:
    """In the `sort` order, newest first by default.

    `q` is folded like search_text, so ״ and " or niqqud don't matter.
    """
    search = fold_text(q) if q else ""
    async with conn.transaction():
        rows, total, counts = await repo.list_records(
            conn,
            search=search or None,
            status=status,
            needs_review=needs_review,
            sender=sender,
            form_type=form_type,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    return RecordList(
        items=[_to_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        counts=RecordCounts(**counts),
    )


# A file, not a page: enough for every record of the demo, small enough to build in memory.
MAX_EXPORT = 5000


async def export_records(
    conn: AsyncConnection,
    user: User,
    *,
    export_format: str,
    now: datetime,
    q: str | None = None,
    status: str | None = None,
    needs_review: bool | None = None,
    sender: str | None = None,
    form_type: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = "-created_at",
) -> list[Record]:
    """Every record the list shows with these filters, and an export_log row (D19).

    More than MAX_EXPORT is refused rather than cut, so a file never silently
    misses records.
    """
    search = fold_text(q) if q else ""
    async with conn.transaction():
        rows = await repo.export_records(
            conn,
            search=search or None,
            status=status,
            needs_review=needs_review,
            sender=sender,
            form_type=form_type,
            date_from=date_from,
            date_to=date_to,
            sort=sort,
            limit=MAX_EXPORT + 1,
        )
        if len(rows) > MAX_EXPORT:
            raise RecordProblem(
                422,
                "export_too_large",
                f"יותר מ־{MAX_EXPORT:,} רשומות. צמצמי את הסינון ונסי שוב",
            )
        await repo.insert_export_log(
            conn, user_id=user.id, export_format=export_format, record_count=len(rows), now=now
        )
    return [to_record(row) for row in rows]


# --- Rules


def _record_needs_review(fields: RecordFields, central: list[FormField], issues: list[Issue]):
    named = [getattr(fields, name) for name in RecordFields.model_fields]
    return any(f.needs_review for f in named + central) or any(is_blocking(i) for i in issues)


def rerun_rules(record: Record, *, today: date) -> Record:
    """apply_rules on one record: its shared fields, central numbers and its one commitment."""
    form = Form(
        form_id=record.record_id,
        file_id="",
        source_file=record.source_file,
        page_number=record.page_number,
        continuation_pages=record.continuation_pages,
        processing_status="ok",
        error=None,
        applied_rotation=0,
        form_type=record.form_type,
        fields=FormFields(**{name: getattr(record.fields, name) for name in SHARED}),
        central_numbers=record.central_numbers,
        commitment_numbers=[record.fields.commitment_number],
        issues=record.issues,
        needs_review=record.needs_review,
    )
    ruled = apply_rules(form, today=today)
    fields = RecordFields(
        **{name: getattr(ruled.fields, name) for name in SHARED},
        commitment_number=ruled.commitment_numbers[0],
    )
    return record.model_copy(
        update={
            "fields": fields,
            "central_numbers": ruled.central_numbers,
            "needs_review": _record_needs_review(fields, ruled.central_numbers, record.issues),
        }
    )


async def _keep_duplicate_flag(conn: AsyncConnection, before: Record, after: Record) -> Record:
    """apply_rules doesn't know other records, so DUPLICATE_RECORD (set on save, A4) is
    kept here: carried while the number stays, checked again when it changes.
    Confirming the field still resolves it."""
    old, new = before.fields.commitment_number, after.fields.commitment_number
    if not new.value:
        return after
    if new.value == old.value:
        duplicate = any(issue.code == "DUPLICATE_RECORD" for issue in old.issues)
    else:
        await repo.lock_commitments(conn, [new.value])
        duplicate = await repo.commitment_taken(conn, new.value, except_id=after.record_id)
    if not duplicate:
        return after
    flagged = new.model_copy(
        update={
            "issues": [*new.issues, make_issue("DUPLICATE_RECORD")],
            "needs_review": not new.confirmed,
        }
    )
    fields = after.fields.model_copy(update={"commitment_number": flagged})
    return after.model_copy(
        update={
            "fields": fields,
            "needs_review": _record_needs_review(fields, after.central_numbers, after.issues),
        }
    )


async def _rerun(conn: AsyncConnection, saved: Record, edited: Record, *, today: date) -> Record:
    """The rules on `edited`; `saved` is the record as it is in the DB, for the duplicate check."""
    return await _keep_duplicate_flag(conn, saved, rerun_rules(edited, today=today))


# --- Changing


async def _locked(conn: AsyncConnection, record_id: str, version: int | None) -> dict:
    """The record's row, locked, after the checks every change makes first."""
    row = await repo.get_record(conn, record_id, lock=True)
    if row is None:
        raise _not_found()
    if row["status"] == "approved":
        raise RecordProblem(409, "record_approved", "הרשומה כבר אושרה, ואי אפשר לשנות אותה")
    if version is not None and row["version"] != version:
        raise RecordProblem(409, "version_conflict", "הרשומה עודכנה בחלון אחר. טענו אותה מחדש")
    return row


def _edit(field: FormField, edit: FieldEdit | ListItemEdit, name: str, events: list):
    """SPEC 7.4: a new value is corrected and no longer confirmed; raw never changes."""
    sent = edit.model_fields_set
    update: dict = {}
    if "value" in sent:
        value = edit.value.strip() if edit.value else ""
        update |= {"value": value or None, "corrected": True, "confirmed": False}
        events.append(("corrected", name))
    if "confirmed" in sent and edit.confirmed is not None:
        update["confirmed"] = edit.confirmed
        events.append(("confirmed", name))
    return field.model_copy(update=update)


_NEW_ITEM = FormField(
    raw=None,
    value=None,
    model_status="not_found",
    evidence=None,
    issues=[],
    needs_review=False,
    corrected=False,
    confirmed=False,
)


def _apply_patch(record: Record, patch: RecordPatch) -> tuple[Record, list, bool]:
    """The record with the user's edits, the events to log, and whether a shared field moved."""
    events: list[tuple[str, str]] = []
    fields = record.fields
    edited = patch.fields.model_fields_set if patch.fields else set()
    for name in edited:
        edit = getattr(patch.fields, name)
        if edit is not None:
            fields = fields.model_copy(
                update={name: _edit(getattr(fields, name), edit, name, events)}
            )
    central = record.central_numbers
    if patch.central_numbers is not None:
        central = []
        for position, item in enumerate(patch.central_numbers):
            if item.idx is None:
                base = _NEW_ITEM
            elif 0 <= item.idx < len(record.central_numbers):
                base = record.central_numbers[item.idx]
            else:
                raise RecordProblem(422, "validation", f"אין מספר מרכזי במקום {item.idx}")
            central.append(_edit(base, item, f"central_numbers[{position}]", events))
        if len(central) < len(record.central_numbers):  # an item was removed
            events.append(("corrected", "central_numbers"))
    shared = bool(edited & set(SHARED)) or patch.central_numbers is not None
    patched = record.model_copy(update={"fields": fields, "central_numbers": central})
    return patched, events, shared


async def _save(conn: AsyncConnection, record: Record, now: datetime) -> None:
    fields = record.fields
    await repo.update_record(
        conn,
        record_id=record.record_id,
        needs_review=record.needs_review,
        fields=fields.model_dump(mode="json"),
        central_numbers=[item.model_dump(mode="json") for item in record.central_numbers],
        national_id=fields.national_id.value,
        commitment_number=fields.commitment_number.value,
        central_values=[item.value for item in record.central_numbers if item.value],
        first_name=fields.first_name.value,
        last_name=fields.last_name.value,
        sender=fields.sender.value,
        received_date=_iso_date(fields.received_date.value),
        search_text=search_text(record),
        now=now,
    )


async def _log(conn, record_id: str, events: Iterable, user: User, now: datetime) -> None:
    for action, field in events:
        await repo.insert_event(
            conn, record_id=record_id, action=action, user_id=user.id, now=now, field=field
        )


async def patch_record(
    conn: AsyncConnection,
    record_id: str,
    patch: RecordPatch,
    user: User,
    *,
    today: date,
    now: datetime,
) -> RecordPatchResponse:
    """Correct or confirm fields and run the rules again. A shared field changes in the
    form's other records too (A3), so they never disagree; an approved one stops it."""
    async with conn.transaction():
        row = await _locked(conn, record_id, patch.version)
        record = to_record(row)
        patched, events, shared = _apply_patch(record, patch)
        sibling_rows = await repo.get_siblings(conn, row, lock=True) if shared else []
        if any(sibling["status"] == "approved" for sibling in sibling_rows):
            raise RecordProblem(
                409,
                "sibling_approved",
                "רשומה אחרת מאותו טופס כבר אושרה, ולכן אי אפשר לשנות את השדות המשותפים",
            )
        ruled = await _rerun(conn, record, patched, today=today)
        await _save(conn, ruled, now)
        await _log(conn, record_id, events, user, now)

        shared_events = [
            (action, field) for action, field in events if field != "commitment_number"
        ]
        for sibling_row in sibling_rows:
            sibling = to_record(sibling_row)
            copied = sibling.model_copy(
                update={
                    "fields": sibling.fields.model_copy(
                        update={name: getattr(ruled.fields, name) for name in SHARED}
                    ),
                    "central_numbers": ruled.central_numbers,
                }
            )
            await _save(conn, await _rerun(conn, sibling, copied, today=today), now)
            await _log(conn, sibling.record_id, shared_events, user, now)

        saved = to_record(await repo.get_record(conn, record_id))
        siblings = [to_record(await repo.get_record(conn, s["id"])) for s in sibling_rows]
    return RecordPatchResponse(record=saved, siblings=siblings)


async def approve_record(
    conn: AsyncConnection,
    record_id: str,
    body: ApproveRequest,
    user: User,
    *,
    today: date,
    now: datetime,
) -> Record:
    """Run the rules again and approve, unless a field still needs review (D3).

    Only fields block: an issue on the whole record (a rotation or page grouping
    that is unsure) has nothing to confirm, so it stays shown and doesn't block.
    """
    async with conn.transaction():
        record = to_record(await _locked(conn, record_id, body.version))
        ruled = await _rerun(conn, record, record, today=today)
        blocking = blocking_fields(ruled.fields, ruled.central_numbers)
        if blocking:
            raise RecordProblem(
                409,
                "review_required",
                "יש שדות שעדיין דורשים בדיקה",
                blocking_fields=blocking,
            )
        if ruled != record:  # e.g. a received date that is now out of range
            await _save(conn, ruled, now)
        await repo.approve_record(conn, record_id, user_id=user.id, now=now)
        await _log(conn, record_id, [("approved", None)], user, now)
        return to_record(await repo.get_record(conn, record_id))


async def approve_many(
    conn: AsyncConnection,
    items: list[BulkApproveItem],
    user: User,
    *,
    today: date,
    now: datetime,
) -> BulkApproveResponse:
    """Approve all ready (D20): each record on its own transaction, so one that is
    skipped never undoes the others."""
    approved, skipped = [], []
    for item in items:
        try:
            approved.append(
                await approve_record(
                    conn,
                    item.record_id,
                    ApproveRequest(version=item.version),
                    user,
                    today=today,
                    now=now,
                )
            )
        except RecordProblem as problem:
            skipped.append(
                SkippedRecord(
                    record_id=item.record_id,
                    type=problem.type,
                    blocking_fields=problem.blocking_fields,
                )
            )
    return BulkApproveResponse(approved=approved, skipped=skipped)


async def delete_record(conn: AsyncConnection, record_id: str) -> None:
    """Delete a pending record (A5). Approved records stay."""
    async with conn.transaction():
        row = await _locked(conn, record_id, version=None)
        await repo.delete_record(conn, row["id"], row["page_id"])
