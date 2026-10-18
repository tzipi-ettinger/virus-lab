"""Records endpoints: list/search/filter, get, patch, approve, page image.

DRAFT for A1 (docs/GUIDELINES-V2-CHANGES.md, section 4.2): the signatures are the
contract, the bodies return 501 until storage/repo.py and rules/engine.py are filled.

Owner: B
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from app.schemas.api import (
    ApproveRequest,
    Problem,
    Record,
    RecordList,
    RecordPatch,
    RecordPatchResponse,
    RecordStatus,
)

router = APIRouter(prefix="/api/v1")

_NOT_FOUND = {404: {"model": Problem, "description": "No such record"}}
_CONFLICT = {409: {"model": Problem, "description": 'Stale version (type "version_conflict")'}}


def _not_implemented() -> HTTPException:
    return HTTPException(status_code=501, detail="Not implemented yet")


@router.get("/records")
def list_records(
    q: Annotated[
        str | None, Query(description="Free text: name, national ID, central or commitment number")
    ] = None,
    status: RecordStatus | None = None,
    sender: str | None = None,
    date_from: Annotated[date | None, Query(description="received_date, inclusive")] = None,
    date_to: Annotated[date | None, Query(description="received_date, inclusive")] = None,
    needs_review: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RecordList:
    """Newest first, then page number, then commitment order.

    `status=approved` is also the hand-off point for the lab's system (D6).
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


@router.get(
    "/pages/{page_id}/image",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}}}, 404: {"model": Problem}},
)
def page_image(page_id: str) -> Response:
    """The rotated, compressed page the fields came from (D4). Sent with Cache-Control: no-store."""
    raise _not_implemented()
