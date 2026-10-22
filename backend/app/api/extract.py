"""POST /api/v1/extract: upload files and read them in the background (pipeline/jobs.py);
GET /api/v1/extract/jobs/{job_id}: how far it got, then the saved records.

Only parses the request and starts pipeline/service.py in a job. The files stay in memory:
Starlette's usual form parsing writes any file over 1MB to a temporary file on
disk, and a patient's form must never land there (SPEC 11.1, D4). So the request
is parsed here with every part kept in memory, and its size is capped first.

Owner: A
"""

import logging
import sys
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated, assert_never

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from google import genai
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr
from python_multipart.multipart import parse_options_header
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.deps import get_pool, require_user
from app.api.errors import ProblemError
from app.clock import israel_today
from app.extraction.cached_provider import CachedProvider
from app.extraction.fake_provider import FakeProvider
from app.extraction.gemini_provider import GeminiProvider
from app.extraction.provider import ExtractionProvider
from app.pipeline.jobs import ExtractJobs, OnProgress, TooManyJobs
from app.pipeline.service import (
    SaveForm,
    TooManyPages,
    UploadedFile,
    extract_files,
)
from app.schemas.api import ExtractJob, ExtractResponse, Problem, User
from app.settings import Settings, get_settings
from app.storage.service import form_saver

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
        401: 'Not signed in ("unauthenticated"). Nothing was read, so the file can be sent again',
        403: 'The request did not come from our own page ("origin_not_allowed")',
        413: 'Request over MAX_REQUEST_MB ("request_too_large"). Too many pages is found '
        'only once the files are split: the job ends with "too_many_pages"',
        415: 'Not multipart/form-data ("unsupported_media_type")',
        503: 'The database is not reachable ("database_unavailable"), or too many uploads '
        'are being read ("too_many_uploads"). Nothing was read, so the file can be sent again',
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


@lru_cache
def _gemini_provider(
    api_keys: tuple[SecretStr, ...], model: str, max_concurrency: int, timeout_s: int
) -> GeminiProvider:
    # One provider per configuration, so its semaphore limits the whole server.
    # The keys stay SecretStr up to here: a traceback through the cache shows ******.
    return GeminiProvider(
        [genai.Client(api_key=key.get_secret_value()) for key in api_keys],
        model,
        max_concurrency=max_concurrency,
        timeout_s=timeout_s,
    )


@lru_cache
def _cached(provider: GeminiProvider) -> CachedProvider:
    # One per provider, so its hit and miss counts add up across requests.
    return CachedProvider(
        provider, provider.fingerprint, name_fingerprint=provider.name_fingerprint
    )


def get_provider(settings: SettingsDep) -> ExtractionProvider:
    match settings.extraction_provider:
        case "fake":
            return _fake_provider()  # no quota to save: the cache is never in front of it
        case "gemini":
            gemini = _gemini_provider(
                settings.gemini_keys(),
                settings.gemini_model,
                settings.max_concurrency,
                settings.provider_timeout_s,
            )
            return _cached(gemini) if settings.extraction_cache else gemini
        case unknown:  # a new provider added to Settings but not here
            assert_never(unknown)


def get_save_form(
    pool: Annotated[AsyncConnectionPool, Depends(get_pool)],
    user: Annotated[User, Depends(require_user)],
) -> SaveForm:
    """Each form is saved as pending records as soon as it is read (B's form_saver)."""
    return form_saver(pool, user)


def get_jobs(request: Request) -> ExtractJobs:
    """One for the whole server (main.py), so the upload and the page asking about
    it meet, and the lifespan can stop the jobs before the database pool closes."""
    return request.app.state.jobs


JobsDep = Annotated[ExtractJobs, Depends(get_jobs)]
UserDep = Annotated[User, Depends(require_user)]


@router.post(
    "/extract",
    status_code=202,
    response_model=ExtractJob,
    responses=_PROBLEMS,
    openapi_extra=_UPLOAD_BODY,
)
async def extract(
    request: Request,
    settings: SettingsDep,
    provider: Annotated[ExtractionProvider, Depends(get_provider)],
    save_form: Annotated[SaveForm, Depends(get_save_form)],
    jobs: JobsDep,
    # Here and not only in get_save_form, so a test that overrides the saver can't
    # turn sign-in off. FastAPI runs require_user once per request either way.
    user: UserDep,
) -> ExtractJob | JSONResponse:
    """Receive the files and read them in the background: 202 with the job at once.

    GET /extract/jobs/{job_id} tells how far it got, and in the end the saved
    records, or why there are none. Each form is saved as soon as it is read, so
    closing the page after this answer loses nothing.

    A request that can't be used is refused here, before anything is read (4xx).
    """
    try:
        uploads = await _read_uploads(request, settings)
    except _BadRequest as exc:
        return _problem(exc.problem)
    today = israel_today()

    async def run(on_progress: OnProgress) -> ExtractResponse | Problem:
        try:
            result = await extract_files(
                uploads,
                provider,
                today=today,
                max_bytes=settings.max_file_bytes,
                max_pages=settings.max_pages_per_request,
                max_concurrency=settings.max_concurrency,
                save_form=save_form,
                on_progress=on_progress,
            )
        except TooManyPages as exc:
            return Problem(type="too_many_pages", title=exc.message, status=413)
        if result.quota_message is not None and not result.forms:
            # Nothing was saved, so the file can be sent again.
            return Problem(type="quota_exhausted", title=result.quota_message, status=503)
        return ExtractResponse(
            files=result.files,
            records=[record for form in result.forms for record in form.records],
            failed_pages=result.failed_pages,
            quota_exhausted=result.quota_exhausted,
        )

    try:
        return jobs.start(user.id, run)
    except TooManyJobs as exc:
        return _problem(Problem(type="too_many_uploads", title=exc.message, status=503))


@router.get(
    "/extract/jobs/{job_id}",
    responses={404: {"model": Problem, "description": 'Unknown or forgotten ("job_not_found")'}},
)
def extract_job(job_id: str, jobs: JobsDep, user: UserDep) -> ExtractJob:
    """How far the upload got, and its answer once it is over. 404 for another
    user's job, and for any job after a server restart or FINISHED_TTL_S after it
    ended: some forms may be saved, so the page checks the records screen."""
    job = jobs.get(job_id, user.id)
    if job is None:
        raise ProblemError(404, "job_not_found", "הקריאה של הקובץ הזה לא נמצאה בשרת")
    return job


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
