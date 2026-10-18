"""Runs the stages for one upload: split -> extract upright -> assemble -> apply_rules.

A few pages at a time, so the model calls overlap. One page failing never stops
the others (FR-12): it becomes a FailedPage. A used-up quota is the exception:
every further call would fail too, so the pages not started yet are failed
without a call, and the pages already in flight are allowed to finish.

Each page is saved as soon as it is read (`save_page`), not at the end, so a
crash or restart in the middle of a long upload keeps the pages already read
(and the quota spent on them), and they show on the records screen at once.
Closing the tab does not stop an upload: the server finishes it either way.

Logs carry only form_id, timings and error types, never names, IDs, file names
or the model's text (SPEC 11.1).

Owner: A
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date

from app.extraction.provider import ExtractionProvider, PageImage, ProviderError, QuotaExhausted
from app.pipeline.assemble import assemble, form_id
from app.pipeline.ingest import InvalidFile, SourcePage, split_pages_async
from app.pipeline.orient import extract_upright
from app.rules.engine import apply_rules
from app.schemas.api import ErrorCode, ErrorInfo, FailedPage, FileResult, Form, Record

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR = "שגיאה לא צפויה בעיבוד העמוד. אפשר לנסות שוב"
SAVE_FAILED = "העמוד נקרא, אבל השמירה נכשלה. אפשר לנסות שוב"


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    data: bytes = field(repr=False)  # a log line or traceback must never carry the document


@dataclass(frozen=True)
class ExtractedPage:
    form: Form  # after apply_rules
    image: PageImage  # the image the fields were read from, saved for the preview (D4)
    calls: int
    seconds: float
    records: list[Record] = field(default_factory=list)  # what save_page stored


# Saves one page and returns its records. Called once per page, never two at a time.
SavePage = Callable[[ExtractedPage], Awaitable[list[Record]]]


@dataclass(frozen=True)
class ExtractionResult:
    files: list[FileResult]
    pages: list[ExtractedPage]  # in upload order: file, then page number
    failed_pages: list[FailedPage]
    quota_message: str | None = None  # the provider's Hebrew message, once the quota ran out

    @property
    def quota_exhausted(self) -> bool:
        return self.quota_message is not None


class TooManyPages(Exception):
    """The whole upload is over the page limit. `message` is shown to the user, in Hebrew."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def extract_files(
    files: Sequence[UploadedFile],
    provider: ExtractionProvider,
    *,
    today: date,
    max_bytes: int,
    max_pages: int,
    max_concurrency: int,
    save_page: SavePage | None = None,
) -> ExtractionResult:
    """Extract every page of every file. Raises TooManyPages before any model call.

    An invalid file is reported in `files` and the others go on. `today` is passed
    to the rules (the caller uses clock.israel_today). A page that `save_page`
    fails on is reported failed, so the response never shows unsaved records.
    """
    if max_concurrency < 1:  # Semaphore(0) would hang the request without an error
        raise ValueError(f"max_concurrency must be at least 1, got {max_concurrency}")
    file_results, pages = await _split_all(files, max_bytes=max_bytes, max_pages=max_pages)
    if len(pages) > max_pages:
        raise TooManyPages(f"בהעלאה {len(pages)} עמודים. המקסימום הוא {max_pages}")

    semaphore = asyncio.Semaphore(max_concurrency)
    # One save at a time within this upload: two pages with the same commitment
    # number saved at once could each miss the other in the duplicate check. Two
    # uploads at once can still race; only the database can prevent that.
    save_lock = asyncio.Lock()
    quota_message: str | None = None

    async def run(page: SourcePage) -> ExtractedPage | FailedPage:
        nonlocal quota_message
        page_id = form_id(page.file_id, page.page_number)
        try:
            async with semaphore:
                if quota_message is not None:
                    return _failed(page, quota_message, code="QUOTA_EXHAUSTED")
                started = time.perf_counter()
                oriented = await extract_upright(provider, page)
            seconds = time.perf_counter() - started
            form = apply_rules(assemble(oriented), today=today)
        except QuotaExhausted as exc:
            logger.warning("quota exhausted at %s", page_id)
            quota_message = exc.message
            return _failed(page, exc.message, code="QUOTA_EXHAUSTED")
        except ProviderError as exc:
            logger.warning("page failed: %s (%s)", page_id, type(exc).__name__)
            return _failed(page, exc.message)
        except Exception as exc:  # a bug on one page must not fail the others
            # Not logger.exception: the traceback can hold the model's text.
            logger.error("page failed unexpectedly: %s (%s)", page_id, type(exc).__name__)
            return _failed(page, UNEXPECTED_ERROR)
        logger.info(
            "page done: %s in %.1fs, %d calls, rotation %d%s",
            page_id,
            seconds,
            oriented.calls,
            oriented.applied_rotation,
            ", unresolved" if oriented.unresolved else "",
        )
        page_result = ExtractedPage(
            form=form, image=oriented.image, calls=oriented.calls, seconds=seconds
        )
        if save_page is None:
            return page_result
        try:
            async with save_lock:
                records = await save_page(page_result)
        except Exception as exc:
            logger.error("page not saved: %s (%s)", page_id, type(exc).__name__)
            return _failed(page, SAVE_FAILED)
        return replace(page_result, records=records)

    outcomes = await asyncio.gather(*(run(page) for page in pages))
    return ExtractionResult(
        files=file_results,
        pages=[item for item in outcomes if isinstance(item, ExtractedPage)],
        failed_pages=[item for item in outcomes if isinstance(item, FailedPage)],
        quota_message=quota_message,
    )


async def _split_all(
    files: Sequence[UploadedFile], *, max_bytes: int, max_pages: int
) -> tuple[list[FileResult], list[SourcePage]]:
    results, pages = [], []
    for upload in files:
        file_id = f"f_{secrets.token_hex(6)}"
        try:
            source = await split_pages_async(
                file_id, upload.filename, upload.data, max_bytes=max_bytes, max_pages=max_pages
            )
        except InvalidFile as exc:
            error = ErrorInfo(code="INVALID_FILE", message=exc.message)
            results.append(_file_result(file_id, upload.filename, 0, error))
            continue
        except Exception as exc:  # a bug on one file must not fail the others
            logger.error("file failed unexpectedly: %s (%s)", file_id, type(exc).__name__)
            error = ErrorInfo(code="EXTRACTION_FAILED", message=UNEXPECTED_ERROR)
            results.append(_file_result(file_id, upload.filename, 0, error))
            continue
        results.append(_file_result(file_id, upload.filename, len(source), None))
        pages.extend(source)
    return results, pages


def _file_result(
    file_id: str, filename: str, page_count: int, error: ErrorInfo | None
) -> FileResult:
    return FileResult(
        file_id=file_id,
        filename=filename,
        page_count=page_count,
        status="error" if error else "ok",
        error=error,
    )


def _failed(page: SourcePage, message: str, *, code: ErrorCode = "EXTRACTION_FAILED") -> FailedPage:
    return FailedPage(
        file_id=page.file_id,
        source_file=page.filename,
        page_number=page.page_number,
        error=ErrorInfo(code=code, message=message),
    )
