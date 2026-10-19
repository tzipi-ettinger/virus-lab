"""Records endpoints: list/search/filter, export, get, patch, approve (one or many),
delete, page image and the senders list.

Only parses the request and calls storage/review.py, which holds the logic.
The export file itself is written by export/records_export.py.

Owner: B
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from psycopg_pool import AsyncConnectionPool

from app.api.errors import ProblemError
from app.auth.deps import get_pool, require_user, utc_now
from app.clock import israel_today
from app.export import records_export
from app.rules.senders import sender_names
from app.schemas.api import (
    ApproveRequest,
    BulkApproveRequest,
    BulkApproveResponse,
    FormType,
    Problem,
    Record,
    RecordList,
    RecordPatch,
    RecordPatchResponse,
    RecordSort,
    RecordStatus,
    User,
)
from app.storage import repo, review

# Every records endpoint needs a signed-in user (Dev-B plan 2.6).
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_user)],
    responses={401: {"model": Problem, "description": 'No valid session ("unauthenticated")'}},
)

_NOT_FOUND = {404: {"model": Problem, "description": "No such record"}}


PoolDep = Annotated[AsyncConnectionPool, Depends(get_pool)]
UserDep = Annotated[User, Depends(require_user)]  # the same call as the router's
NowDep = Annotated[datetime, Depends(utc_now)]


async def _run[T](call: Awaitable[T]) -> T:
    """A review call, with its RecordProblem answered as a Problem."""
    try:
        return await call
    except review.RecordProblem as exc:
        error = ProblemError(exc.status, exc.type, exc.title)
        error.problem.blocking_fields = exc.blocking_fields
        raise error from None


@dataclass(frozen=True)
class RecordFilters:
    """The filters of the records screen. Every one is optional and they combine with AND."""

    q: Annotated[
        str | None, Query(description="Free text: name, national ID, central or commitment number")
    ] = None
    status: RecordStatus | None = None
    needs_review: bool | None = None
    sender: Annotated[str | None, Query(description="A name from GET /senders")] = None
    form_type: FormType | None = None
    date_from: Annotated[date | None, Query(description="received_date, inclusive")] = None
    date_to: Annotated[date | None, Query(description="received_date, inclusive")] = None
    # Not a filter, but the list and the export take it alike, so the file is in the
    # order the screen shows.
    sort: Annotated[
        RecordSort,
        Query(description='A column, ascending; "-" in front for descending. Empty values last.'),
    ] = "-created_at"


FiltersDep = Annotated[RecordFilters, Depends()]
ExportFormat = Literal["csv", "json"]


@router.get("/records")
async def list_records(
    filters: FiltersDep,
    pool: PoolDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordList:
    """In the `sort` order (newest first by default), then page number, then
    commitment order.

    `status=approved` is also the hand-off point for the lab's system (D6).
    """
    async with pool.connection() as conn:
        return await review.list_records(conn, **vars(filters), limit=limit, offset=offset)


# Fixed paths under /records go before /records/{record_id}, or it would take them.


@router.post("/records/approve")
async def approve_many(
    body: BulkApproveRequest, pool: PoolDep, user: UserDep, now: NowDep
) -> BulkApproveResponse:
    """Approve all ready (D20): each record is checked and saved on its own.

    Always 200. A record with a field still flagged, a stale version or one already
    approved is listed in `skipped` with the reason, and the others are approved.
    """
    async with pool.connection() as conn:
        return await review.approve_many(conn, body.items, user, today=israel_today(now), now=now)


_MEDIA_TYPES = {"csv": "text/csv; charset=utf-8", "json": "application/json"}
_WRITERS = {"csv": records_export.to_csv, "json": records_export.to_json}


@router.get(
    "/records/export",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}, "application/json": {}},
            "description": "A file to download (Content-Disposition: attachment): "
            "CSV in UTF-8 with BOM (SPEC 10), or JSON as a list of Record.",
        },
        422: {
            "model": Problem,
            "description": 'More than 5,000 records match ("export_too_large")',
        },
    },
)
async def export_records(
    filters: FiltersDep,
    export_format: Annotated[ExportFormat, Query(alias="format")],
    pool: PoolDep,
    user: UserDep,
    now: NowDep,
) -> Response:
    """Every record that matches the screen's filters, without paging (D19).

    The same filters as GET /records: with no status, every record. Sent with
    Cache-Control: no-store, and logged in export_log without values.
    """
    async with pool.connection() as conn:
        records = await _run(
            review.export_records(conn, user, export_format=export_format, now=now, **vars(filters))
        )
    filename = records_export.export_filename(export_format, israel_today(now))
    return Response(
        _WRITERS[export_format](records),
        media_type=_MEDIA_TYPES[export_format],
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # no-store: the file holds patients' details (D4).
            "Cache-Control": "no-store",
        },
    )


@router.get("/records/{record_id}", responses=_NOT_FOUND)
async def get_record(record_id: str, pool: PoolDep) -> Record:
    async with pool.connection() as conn:
        return await _run(review.get_record(conn, record_id))


@router.patch(
    "/records/{record_id}",
    responses={
        **_NOT_FOUND,
        409: {
            "model": Problem,
            "description": 'Stale version ("version_conflict"), an approved record '
            '("record_approved"), or a shared field while another record of the form is '
            'approved ("sibling_approved")',
        },
        422: {"model": Problem, "description": 'No central number at that idx ("validation")'},
    },
)
async def patch_record(
    record_id: str, body: RecordPatch, pool: PoolDep, user: UserDep, now: NowDep
) -> RecordPatchResponse:
    """Correct or confirm fields, rerun apply_rules (SPEC 7.4) and save.

    A shared field (names, ID, date, sender, central numbers) changes in the form's
    other records too, returned in `siblings` (A3). Approved records are read-only (A6).
    """
    async with pool.connection() as conn:
        return await _run(
            review.patch_record(conn, record_id, body, user, today=israel_today(now), now=now)
        )


@router.post(
    "/records/{record_id}/approve",
    responses={
        **_NOT_FOUND,
        409: {
            "model": Problem,
            "description": 'Stale version ("version_conflict"), or fields still flagged '
            '("review_required", listed in blocking_fields)',
        },
    },
)
async def approve_record(
    record_id: str, body: ApproveRequest, pool: PoolDep, user: UserDep, now: NowDep
) -> Record:
    """Rerun the rules; approve only if no field still needs review (D3)."""
    async with pool.connection() as conn:
        return await _run(
            review.approve_record(conn, record_id, body, user, today=israel_today(now), now=now)
        )


@router.delete(
    "/records/{record_id}",
    status_code=204,
    response_class=Response,
    responses={
        **_NOT_FOUND,
        409: {"model": Problem, "description": 'Approved records stay ("record_approved")'},
    },
)
async def delete_record(record_id: str, pool: PoolDep) -> Response:
    """Delete a pending record (A5). The form's pages go too once no record needs them."""
    async with pool.connection() as conn:
        await _run(review.delete_record(conn, record_id))
    return Response(status_code=204)


@router.get("/senders")
def senders() -> list[str]:
    """The closed list of senders (SPEC 5.5), for the dropdown and the filter."""
    return sender_names()


@router.get(
    "/pages/{page_id}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/jpeg": {}}},
        404: {"model": Problem, "description": 'No such page ("page_not_found")'},
    },
)
async def page_image(page_id: str, pool: PoolDep) -> Response:
    """The rotated, compressed page the fields came from (D4). Sent with Cache-Control: no-store."""
    async with pool.connection() as conn:
        jpeg = await repo.get_page_image(conn, page_id)
    if jpeg is None:
        raise ProblemError(404, "page_not_found", "העמוד לא נמצא")
    # no-store: a patient's form must not stay in the browser's or a proxy's cache (D4).
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
