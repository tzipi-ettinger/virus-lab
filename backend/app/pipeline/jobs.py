"""Uploads read in the background. POST /extract receives the files, starts a job
and answers 202 at once; the page asks GET /extract/jobs/{job_id} until it is over.

Why: a page can take minutes (there is no time limit on it) and a 26-page file more.
One request held open that long breaks on any proxy or network timeout, and then
the page can't tell what was saved. Now the request ends once the files are in.

Kept in this server process's memory only, like the quota state. A restart (a
deploy) gives the running jobs SHUTDOWN_GRACE_S to finish, stops the rest, and
forgets every job: the page then gets 404 and shows the upload as stopped. Each
form is saved as soon as it is read, so what was read before that is on the
records screen. A finished job is kept FINISHED_TTL_S for the page to collect.

Every signed-in user sees every job, as on the records screen; the user who
started it counts only for MAX_RUNNING_PER_USER. Only counts, the result and the
problem are kept: never the files once the job is over (SPEC 11.1).

Owner: A
"""

import asyncio
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from app.schemas.api import ExtractJob, ExtractResponse, Problem

logger = logging.getLogger(__name__)

# Jobs running at once, on the whole server and per user. Each one holds its files
# in memory (up to MAX_REQUEST_MB) until it ends. The page sends one file at a time,
# so a user reaches the limit only from several tabs at once.
MAX_RUNNING = 10
MAX_RUNNING_PER_USER = 3
FINISHED_TTL_S = 15 * 60
# Render waits 30 seconds after SIGTERM before it kills the process.
SHUTDOWN_GRACE_S = 20.0

# The job ended without an answer: a bug, or the server stopping. Forms read before
# that are saved, so this is not "send it again" (the same as a cut-off request).
STOPPED = Problem(
    type="extraction_stopped",
    title="הקריאה נעצרה באמצע",
    status=500,
    detail="ייתכן שחלק מהעמודים כבר נשמרו. כדאי לבדוק במסך הרשומות לפני ששולחים שוב",
)
BUSY = "יש כרגע הרבה העלאות שנקראות. אפשר לשלוח שוב בעוד כמה דקות"
BUSY_FOR_USER = "כבר נקראות כמה העלאות שלך. אפשר לשלוח שוב כשאחת מהן מסתיימת"

# (pages read, pages in the upload), as extract_files reports them.
OnProgress = Callable[[int, int], None]
# The job's work: reads the files, and returns the answer or why there is none.
Run = Callable[[OnProgress], Awaitable[ExtractResponse | Problem]]


class TooManyJobs(Exception):
    """Over MAX_RUNNING or MAX_RUNNING_PER_USER. `message` is shown to the user, in Hebrew."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class _Job:
    user_id: str
    task: asyncio.Task[None] | None = None
    done: int = 0
    total: int = 0
    outcome: ExtractResponse | Problem | None = None  # None while running
    finished_at: float | None = None


class ExtractJobs:
    def __init__(
        self,
        *,
        max_running: int = MAX_RUNNING,
        max_running_per_user: int = MAX_RUNNING_PER_USER,
        finished_ttl_s: float = FINISHED_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max_running = max_running
        self._max_running_per_user = max_running_per_user
        self._finished_ttl_s = finished_ttl_s
        self._clock = clock
        self._jobs: dict[str, _Job] = {}

    def start(self, user_id: str, run: Run) -> ExtractJob:
        """Start `run` in the background. Raises TooManyJobs, before starting it."""
        self._forget_old()
        running = [job for job in self._jobs.values() if job.outcome is None]
        if len(running) >= self._max_running:
            raise TooManyJobs(BUSY)
        if sum(job.user_id == user_id for job in running) >= self._max_running_per_user:
            raise TooManyJobs(BUSY_FOR_USER)
        job_id = secrets.token_urlsafe(16)
        job = _Job(user_id=user_id)
        self._jobs[job_id] = job
        # The job holds its task, so it isn't garbage-collected while it runs.
        job.task = asyncio.create_task(self._run(job, run))
        return _view(job_id, job)

    def get(self, job_id: str) -> ExtractJob | None:
        """None for a job that doesn't exist or was forgotten. Any signed-in user may
        ask, like the records screen, where everyone sees everyone's records."""
        self._forget_old()
        job = self._jobs.get(job_id)
        if job is None:
            return None
        return _view(job_id, job)

    async def shutdown(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Give the running jobs `grace_s` to finish, then stop them. Called before
        the database pool closes, so no job is left saving without one."""
        tasks = [job.task for job in self._jobs.values() if job.task is not None]
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=grace_s)
        if pending:
            logger.warning("stopping %d upload jobs at shutdown", len(pending))
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    async def _run(self, job: _Job, run: Run) -> None:
        def on_progress(done: int, total: int) -> None:
            job.done, job.total = done, total

        try:
            outcome = await run(on_progress)
        except asyncio.CancelledError:
            self._finish(job, STOPPED)
            raise
        except Exception as exc:
            # Not logger.exception: the traceback can hold the model's text.
            logger.error("upload job failed unexpectedly (%s)", type(exc).__name__)
            outcome = STOPPED
        self._finish(job, outcome)

    def _finish(self, job: _Job, outcome: ExtractResponse | Problem) -> None:
        job.outcome = outcome
        job.finished_at = self._clock()
        job.task = None  # lets the files it held be freed

    def _forget_old(self) -> None:
        cutoff = self._clock() - self._finished_ttl_s
        for job_id in [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < cutoff
        ]:
            del self._jobs[job_id]


def _view(job_id: str, job: _Job) -> ExtractJob:
    outcome = job.outcome
    if outcome is None:
        status = "running"
    else:
        status = "failed" if isinstance(outcome, Problem) else "done"
    return ExtractJob(
        job_id=job_id,
        status=status,
        done=job.done,
        total=job.total,
        result=outcome if isinstance(outcome, ExtractResponse) else None,
        problem=outcome if isinstance(outcome, Problem) else None,
    )
