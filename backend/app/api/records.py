"""Records endpoints: list/search/filter, export, get, patch, approve (one or many),
delete, page image and the senders list.

DRAFT for A1 (docs/GUIDELINES-V2-CHANGES.md, section 4.2): the signatures are the
contract, the bodies return 501 until storage/repo.py and rules/engine.py are filled.

Owner: B
"""

from dataclasses import dataclass
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from psycopg_pool import AsyncConnectionPool

from app.api.errors import ProblemError
from app.auth.deps import get_pool, require_user
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
    RecordStatus,
)
from app.storage import repo

# Every records endpoint needs a signed-in user (Dev-B plan 2.6).
router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(require_user)],
    responses={401: {"model": Problem, "description": 'No valid session ("unauthenticated")'}},
)

_NOT_FOUND = {404: {"model": Problem, "description": "No such record"}}
_CONFLICT = {409: {"model": Problem, "description": 'Stale version (type "version_conflict")'}}


def _not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail="Not implemented yet")


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


FiltersDep = Annotated[RecordFilters, Depends()]
ExportFormat = Literal["csv", "json"]


@router.get("/records")
def list_records(
    filters: FiltersDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordList:
    """Newest first, then page number, then commitment order.

    `status=approved` is also the hand-off point for the lab's system (D6).
    """
    raise _not_implemented()


# Fixed paths under /records go before /records/{record_id}, or it would take them.


@router.post("/records/approve")
def approve_many(body: BulkApproveRequest) -> BulkApproveResponse:
    """Approve all ready (D20): each record is checked and saved on its own.

    Always 200. A record with a field still flagged, a stale version or one already
    approved is listed in `skipped` with the reason, and the others are approved.
    """
    raise _not_implemented()


@router.get(
    "/records/export",
    response_class=Response,
    responses={
        200: {
            "content": {"text/csv": {}, "application/json": {}},
            "description": "A file to download (Content-Disposition: attachment): "
            "CSV in UTF-8 with BOM, or JSON as a list of Record.",
        }
    },
)
def export_records(
    filters: FiltersDep,
    export_format: Annotated[ExportFormat, Query(alias="format")],
) -> Response:
    """Every record that matches the screen's filters, without paging (D19).

    Sent with Cache-Control: no-store, and logged in export_log without values.
    """
    raise _not_implemented()


@router.get("/records/{record_id}", responses=_NOT_FOUND)
def get_record(record_id: str) -> Record:
    raise _not_implemented()


@router.patch("/records/{record_id}", responses={**_NOT_FOUND, **_CONFLICT})
def patch_record(record_id: str, body: RecordPatch) -> RecordPatchResponse:
    """Correct or confirm fields, rerun apply_rules (SPEC 7.4) and save.

    Approved records are read-only (A6).
    """
    raise _not_implemented()


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
def approve_record(record_id: str, body: ApproveRequest) -> Record:
    """Rerun the rules; approve only if no field still needs review (D3)."""
    raise _not_implemented()


@router.delete(
    "/records/{record_id}",
    status_code=204,
    response_class=Response,
    responses={
        **_NOT_FOUND,
        409: {"model": Problem, "description": 'Approved records stay ("record_approved")'},
    },
)
def delete_record(record_id: str) -> Response:
    """Delete a pending record (A5)."""
    raise _not_implemented()


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
async def page_image(
    page_id: str, pool: Annotated[AsyncConnectionPool, Depends(get_pool)]
) -> Response:
    """The rotated, compressed page the fields came from (D4). Sent with Cache-Control: no-store."""
    async with pool.connection() as conn:
        jpeg = await repo.get_page_image(conn, page_id)
    if jpeg is None:
        raise ProblemError(404, "page_not_found", "העמוד לא נמצא")
    # no-store: a patient's form must not stay in the browser's or a proxy's cache (D4).
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
