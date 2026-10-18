"""POST /api/v1/extract: upload files, run the pipeline, return the saved records.

Only parses the request and calls pipeline/service.py. The files stay in memory:
Starlette's usual form parsing writes any file over 1MB to a temporary file on
disk, and a patient's form must never land there (SPEC 11.1, D4). So the request
is parsed here with every part kept in memory, and its size is capped first.

Owner: A
"""

import logging
import secrets
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, assert_never
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from python_multipart.multipart import parse_options_header
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.clock import israel_today
from app.extraction.fake_provider import FakeProvider
from app.extraction.provider import ExtractionProvider
from app.pipeline.service import (
    ExtractedPage,
    SavePage,
    TooManyPages,
    UploadedFile,
    extract_files,
)
from app.rules.records import build_records
from app.schemas.api import ExtractResponse, Problem, Record
from app.settings import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Declared by hand: the endpoint reads the request itself, so FastAPI can't infer it.
_UPLOAD_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["files"],
                    "properties": {
                        "files": {
                            "type": "array",
                            "items": {"type": "string", "format": "binary"},
                            "description": "PDF, JPG or PNG files.",
                        }
                    },
                }
            }
        },
    }
}
_PROBLEMS = {
    status: {"model": Problem, "description": description}
    for status, description in {
        400: 'No files ("no_files"), more than MAX_FILES_PER_REQUEST ("too_many_files"), '
        'or an upload that is cut off or broken ("invalid_upload")',
        413: 'Request over MAX_REQUEST_MB ("request_too_large") or over '
        'MAX_PAGES_PER_REQUEST ("too_many_pages")',
        415: 'Not multipart/form-data ("unsupported_media_type")',
        503: 'The daily Gemini quota ran out before any page was saved ("quota_exhausted"): '
        "nothing was saved, so the file can be sent again",
    }.items()
}


class _InMemoryParser(MultiPartParser):
    # Never spill to disk. Memory is bounded by the request size cap below.
    spool_max_size = sys.maxsize


class _RequestTooLarge(Exception):
    pass


class _Body:
    """The request body as the parser reads it: capped at `limit`, keeping its last
    bytes to tell a complete upload from one cut off in the middle. Starlette parses
    a cut-off upload without an error and just drops the unfinished file."""

    _TAIL = 256  # a boundary is at most 70 characters (RFC 2046)

    def __init__(self, stream: AsyncIterator[bytes], limit: int) -> None:
        self._stream = stream
        self._limit = limit
        self.tail = b""

    async def chunks(self) -> AsyncIterator[bytes]:
        received = 0
        async for chunk in self._stream:
            received += len(chunk)
            if received > self._limit:  # Content-Length can be missing or wrong
                raise _RequestTooLarge
            self.tail = (self.tail + chunk)[-self._TAIL :]
            yield chunk

    def is_complete(self, boundary: bytes) -> bool:
        return self.tail.rstrip(b"\r\n").endswith(b"--" + boundary + b"--")


class _BadRequest(Exception):
    def __init__(self, status: int, type_: str, title: str, detail: str | None = None) -> None:
        super().__init__(title)
        self.problem = Problem(type=type_, title=title, status=status, detail=detail)


SettingsDep = Annotated[Settings, Depends(get_settings)]


@lru_cache
def _fake_provider() -> FakeProvider:
    return FakeProvider()


def get_provider(settings: SettingsDep) -> ExtractionProvider:
    match settings.extraction_provider:
        case "fake":
            return _fake_provider()
        case unknown:  # a new provider added to Settings but not here
            assert_never(unknown)


async def records_without_saving(page: ExtractedPage) -> list[Record]:
    """Stand-in for B's save_extracted_page until storage is on main (A2).

    The same records build_records makes, with ids and timestamps, but NOT saved:
    the records API can't find them yet. It lets the review screen be built
    against real responses now. Replaced by one line in get_save_page.
    """
    now = datetime.now(UTC)
    form = page.form
    page_id = f"p_{secrets.token_hex(8)}"
    return [
        Record(
            record_id=str(uuid4()),
            page_id=page_id,
            source_file=form.source_file,
            page_number=form.page_number,
            commitment_index=draft.commitment_index,
            status="pending",
            version=1,
            fields=draft.fields,
            central_numbers=draft.central_numbers,
            issues=draft.issues,
            needs_review=draft.needs_review,
            created_at=now,
            updated_at=now,
            approved_at=None,
        )
        for draft in build_records(form)
    ]


def get_save_page() -> SavePage:
    # TODO(A2): B's save_extracted_page, once storage is on main.
    return records_without_saving


@router.post(
    "/extract",
    response_model=ExtractResponse,
    responses=_PROBLEMS,
    openapi_extra=_UPLOAD_BODY,
)
async def extract(
    request: Request,
    settings: SettingsDep,
    provider: Annotated[ExtractionProvider, Depends(get_provider)],
    save_page: Annotated[SavePage, Depends(get_save_page)],
) -> ExtractResponse | JSONResponse:
    """Read every page of every file and save it as pending records.

    A file or page that fails is reported in `files` / `failed_pages`, and the
    others go on. When the daily quota runs out, the answer says whether sending
    the file again is safe:
    - nothing was saved: 503 quota_exhausted, and the file can be sent again;
    - some pages were saved: 200 with quota_exhausted=true and those records.
      Sending the file again would save them twice.
    Otherwise 200, unless the request itself is unusable (4xx).
    """
    try:
        uploads = await _read_uploads(request, settings)
        result = await extract_files(
            uploads,
            provider,
            today=israel_today(),
            max_bytes=settings.max_file_bytes,
            max_pages=settings.max_pages_per_request,
            max_concurrency=settings.max_concurrency,
            save_page=save_page,
        )
    except TooManyPages as exc:
        return _problem(Problem(type="too_many_pages", title=exc.message, status=413))
    except _BadRequest as exc:
        return _problem(exc.problem)
    if result.quota_message is not None and not result.pages:
        return _problem(Problem(type="quota_exhausted", title=result.quota_message, status=503))
    return ExtractResponse(
        files=result.files,
        records=[record for page in result.pages for record in page.records],
        failed_pages=result.failed_pages,
        quota_exhausted=result.quota_exhausted,
    )


async def _read_uploads(request: Request, settings: Settings) -> list[UploadedFile]:
    if not request.headers.get("content-type", "").lower().startswith("multipart/form-data"):
        raise _BadRequest(415, "unsupported_media_type", "יש לשלוח את הקבצים כ־multipart/form-data")
    limit = settings.max_request_bytes
    too_large = _BadRequest(
        413, "request_too_large", f"ההעלאה גדולה מ־{settings.max_request_mb}MB. אפשר לחלק אותה"
    )
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > limit:
        raise too_large  # before reading a byte

    body = _Body(request.stream(), limit)
    too_many_files = _BadRequest(
        400, "too_many_files", f"אפשר להעלות עד {settings.max_files_per_request} קבצים בבקשה אחת"
    )
    # The parser must stop at the file limit itself: the size cap alone doesn't bound
    # the work, since 60MB can hold a million empty "files", each one an object.
    parser = _InMemoryParser(
        request.headers, body.chunks(), max_files=settings.max_files_per_request, max_fields=10
    )
    try:
        form = await parser.parse()
    except _RequestTooLarge:
        raise too_large from None
    except MultiPartException as exc:
        if str(exc).startswith("Too many files"):  # Starlette's message, pinned by a test
            raise too_many_files from exc
        raise _BadRequest(
            400, "invalid_upload", "לא ניתן לקרוא את ההעלאה", "ייתכן שהיא פגומה. אפשר לשלוח שוב"
        ) from exc
    try:
        boundary = parse_options_header(request.headers["content-type"])[1].get(b"boundary", b"")
        if not body.is_complete(boundary):
            raise _BadRequest(
                400, "invalid_upload", "ההעלאה נקטעה באמצע", "שום דבר לא נשמר. אפשר לשלוח שוב"
            )
        uploads = [
            UploadedFile(filename=item.filename or "upload", data=await item.read())
            for item in form.getlist("files")
            if isinstance(item, UploadFile)
        ]
    finally:
        await form.close()
    if not uploads:
        raise _BadRequest(400, "no_files", "לא נבחרו קבצים")
    return uploads


def _problem(problem: Problem) -> JSONResponse:
    return JSONResponse(
        problem.model_dump(exclude_none=True),
        status_code=problem.status,
        media_type="application/problem+json",
    )
