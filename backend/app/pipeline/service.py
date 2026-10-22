"""Runs the stages for one upload: split -> extract upright (a page with several forms
is cut into one page per form, split.py) -> read the name again, enlarged (names.py)
-> assemble -> apply_rules -> group pages into forms (group.py) -> save each form.

A few pages at a time, so the model calls overlap. One page failing never stops
the others (FR-12): it becomes a FailedPage. A used-up quota is the exception:
every further call would fail too, so the pages not started yet are failed
without a call, and the pages already in flight are allowed to finish.

Each form is saved (`save_form`) as soon as the page after it is read, since only
then is it known whether that page continues it; a file's last form when the file
ends. Not at the end of the upload, so a crash or restart in the middle of a long
upload keeps the forms already read (and the quota spent on them), and they show
on the records screen at once. Closing the tab does not stop an upload: the
server finishes it either way.

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
from app.pipeline.group import FormGroup, ReadPage, join, place, start
from app.pipeline.ingest import (
    SAVE_JPEG_QUALITY,
    SAVE_MAX_SIDE_PX,
    InvalidFile,
    SourcePage,
    split_pages_async,
)
from app.pipeline.names import read_name_closer
from app.pipeline.orient import extract_upright
from app.pipeline.split import form_boxes
from app.rules.engine import apply_rules
from app.schemas.api import ErrorCode, ErrorInfo, FailedPage, FileResult, Form, Record

logger = logging.getLogger(__name__)

UNEXPECTED_ERROR = "שגיאה לא צפויה בעיבוד העמוד. אפשר לנסות שוב"
# Not "send the file again": the file's other forms are saved, and would be saved twice.
SAVE_FAILED = "העמוד נקרא, אבל לא נשמר. כדי לשמור אותו, אפשר להעלות שוב רק את העמוד הזה"


@dataclass(frozen=True)
class UploadedFile:
    filename: str
    data: bytes = field(repr=False)  # a log line or traceback must never carry the document


@dataclass(frozen=True)
class ExtractedForm:
    form: Form  # after apply_rules; continuation_pages lists its later pages
    # The pages to save for the preview (D4), upright, SAVE_MAX_SIDE_PX at
    # SAVE_JPEG_QUALITY (not the larger image the model read): the first page, then
    # each of form.continuation_pages in order.
    images: list[PageImage]
    calls: int
    seconds: float
    records: list[Record] = field(default_factory=list)  # what save_form stored


# Saves one form and returns its records. Called once per form, never two at a time.
SaveForm = Callable[[ExtractedForm], Awaitable[list[Record]]]
# (pages read, pages in the upload): once the files are split, then after each page.
OnProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class ExtractionResult:
    files: list[FileResult]
    forms: list[ExtractedForm]  # in upload order: file, then first page
    failed_pages: list[FailedPage]  # in upload order too
    quota_message: str | None = None  # the provider's Hebrew message, once the quota ran out

    @property
    def quota_exhausted(self) -> bool:
        return self.quota_message is not None


@dataclass(frozen=True)
class _Split:
    """A page with several forms, cut into one page per form (split.py), not read yet."""

    parts: list[SourcePage]
    calls: int  # the calls that found the forms
    seconds: float


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
    save_form: SaveForm | None = None,
    on_progress: OnProgress | None = None,
) -> ExtractionResult:
    """Extract every page of every file. Raises TooManyPages before any model call.

    An invalid file is reported in `files` and the others go on. `today` is passed
    to the rules (the caller uses clock.israel_today). When `save_form` fails on a
    form, all its pages are reported failed, so the response never shows unsaved
    records. `on_progress` counts a page once it is read or failed, in the order
    pages finish, before it is grouped and saved.
    """
    if max_concurrency < 1:  # Semaphore(0) would hang the request without an error
        raise ValueError(f"max_concurrency must be at least 1, got {max_concurrency}")
    file_results, pages = await _split_all(files, max_bytes=max_bytes, max_pages=max_pages)
    if len(pages) > max_pages:
        raise TooManyPages(f"בהעלאה {len(pages)} עמודים. המקסימום הוא {max_pages}")

    semaphore = asyncio.Semaphore(max_concurrency)
    quota_message: str | None = None
    pages_done = 0
    if on_progress is not None:
        on_progress(0, len(pages))

    async def run(page: SourcePage) -> list[ReadPage | FailedPage]:
        nonlocal pages_done
        outcomes = await read_page(page)
        pages_done += 1
        if on_progress is not None:
            on_progress(pages_done, len(pages))
        return outcomes

    async def read_page(page: SourcePage) -> list[ReadPage | FailedPage]:
        """One outcome per form on the page: usually one, several when it was split."""
        outcome = await read(page, split=True)
        if not isinstance(outcome, _Split):
            return [outcome]
        # One part at a time: the semaphore counts pages, and a part is a page too.
        parts = [await read(part, split=False) for part in outcome.parts]
        # The call that found the forms counts against the quota too.
        for index, part in enumerate(parts):
            if isinstance(part, ReadPage):
                parts[index] = replace(
                    part, calls=part.calls + outcome.calls, seconds=part.seconds + outcome.seconds
                )
                break
        return parts

    async def read(page: SourcePage, *, split: bool) -> ReadPage | FailedPage | _Split:
        nonlocal quota_message
        page_id = form_id(page.file_id, page.page_number)
        try:
            async with semaphore:
                if quota_message is not None:
                    return _failed(page, quota_message, code="QUOTA_EXHAUSTED")
                started = time.perf_counter()
                oriented = await extract_upright(provider, page, stop_at_several_forms=split)
                boxes = form_boxes(oriented.extraction) if split else []
                if not boxes:  # a page about to be cut has its names read form by form
                    oriented = await read_name_closer(provider, page, oriented)
            seconds = time.perf_counter() - started
            if boxes:
                logger.info("page split: %s into %d forms", page_id, len(boxes))
                rotation = oriented.applied_rotation
                parts = [
                    await page.crop_async(rotation, box, part)
                    for part, box in enumerate(boxes, start=1)
                ]
                return _Split(parts=parts, calls=oriented.calls, seconds=seconds)
            # Outside the semaphore: it limits model calls, and this is not one.
            saved = await page.render_async(
                oriented.applied_rotation, max_side=SAVE_MAX_SIDE_PX, quality=SAVE_JPEG_QUALITY
            )
            form = assemble(oriented)
            ruled = apply_rules(form, today=today)
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
        return ReadPage(
            form=form,
            ruled=ruled,
            image=oriented.image,
            saved=saved,
            calls=oriented.calls,
            seconds=seconds,
        )

    forms: list[ExtractedForm] = []
    failed_pages: list[FailedPage] = []

    async def close(group: FormGroup | None) -> None:
        # Saves run one at a time, in page order: two forms with the same commitment
        # number saved at once could each miss the other in the duplicate check. Two
        # uploads at once can still race; the database handles that (B's save).
        if group is None:
            return
        extracted = ExtractedForm(
            form=group.form,
            images=group.images,
            calls=sum(page.calls for page in group.pages),
            seconds=sum(page.seconds for page in group.pages),
        )
        if save_form is not None:
            try:
                extracted = replace(extracted, records=await save_form(extracted))
            except Exception as exc:
                logger.error("form not saved: %s (%s)", group.form.form_id, type(exc).__name__)
                # One transaction per form (B): none of its pages was saved.
                failed_pages.extend(_failed_read(page, SAVE_FAILED) for page in group.pages)
                return
        forms.append(extracted)

    # The model calls run in parallel, a few at a time; the pages are grouped and
    # saved in upload order, each one as soon as it and the pages before it are done.
    tasks = [asyncio.ensure_future(run(page)) for page in pages]
    try:
        group: FormGroup | None = None
        previous_file: str | None = None
        # The page before failed or held several forms: a page without a central
        # number may continue it, and there's no telling which form.
        previous_doubtful = False
        for page, task in zip(pages, tasks, strict=True):
            outcomes = await task
            same_file = previous_file == page.file_id
            previous_file = page.file_id
            if len(outcomes) > 1:  # several forms on one page: each a form of its own
                await close(group)
                group = None
                for outcome in outcomes:
                    if isinstance(outcome, FailedPage):
                        failed_pages.append(outcome)
                    else:
                        await close(start(outcome, uncertain=False, today=today))
                previous_doubtful = True
                continue
            [outcome] = outcomes
            if isinstance(outcome, FailedPage):
                await close(group)
                group = None
                failed_pages.append(outcome)
            else:
                open_group = group if same_file else None
                after_failure = same_file and previous_doubtful
                placement = place(outcome, open_group, after_failure=after_failure)
                joined = None
                if placement == "join" and open_group is not None:
                    joined = _join_or_none(open_group, outcome, today=today)
                if joined is not None:
                    group = joined
                else:
                    await close(group)
                    # A join that failed is a doubt like any other: flagged, not attached.
                    uncertain = placement != "new"
                    group = start(outcome, uncertain=uncertain, today=today)
            previous_doubtful = isinstance(outcome, FailedPage)
        await close(group)
    finally:
        # Left over only if the loop itself broke (run() never raises): stop the
        # pages still waiting, and wait for them so none outlives the request.
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    return ExtractionResult(
        files=file_results,
        forms=forms,
        failed_pages=failed_pages,
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


def _join_or_none(group: FormGroup, page: ReadPage, *, today: date) -> FormGroup | None:
    """join(), or None if it raises: the rules on the merged form are new input.

    Without this, a bug there would stop the upload after earlier forms were
    saved, and the 500 would invite sending the file again (saving them twice).
    """
    try:
        return join(group, page, today=today)
    except Exception as exc:
        # Not logger.exception: the traceback can hold the model's text.
        logger.error("join failed: %s (%s)", page.form.form_id, type(exc).__name__)
        return None


def _failed_read(page: ReadPage, message: str) -> FailedPage:
    image = page.image
    return FailedPage(
        file_id=image.file_id,
        source_file=image.filename,
        page_number=image.page_number,
        error=ErrorInfo(code="EXTRACTION_FAILED", message=message),
    )
