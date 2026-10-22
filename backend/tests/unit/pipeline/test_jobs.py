"""ExtractJobs: uploads read in the background. The endpoints are tested in
tests/unit/api/test_extract_jobs.py."""

import asyncio

import pytest

from app.pipeline.jobs import BUSY, BUSY_FOR_USER, STOPPED, ExtractJobs, TooManyJobs
from app.schemas.api import ExtractResponse, Problem

ANSWER = ExtractResponse(files=[], records=[], failed_pages=[])


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


async def answer_after(on_progress, gate: asyncio.Event, outcome=ANSWER):
    on_progress(0, 3)
    on_progress(1, 3)
    await gate.wait()
    return outcome


def test_a_job_runs_in_the_background_and_ends_with_its_answer():
    async def scenario():
        jobs = ExtractJobs()
        gate = asyncio.Event()

        started = jobs.start("u1", lambda progress: answer_after(progress, gate))
        assert (started.status, started.done, started.total) == ("running", 0, 0)

        await asyncio.sleep(0)
        running = jobs.get(started.job_id)
        assert (running.status, running.done, running.total) == ("running", 1, 3)

        gate.set()
        await asyncio.sleep(0)
        return jobs.get(started.job_id)

    done = asyncio.run(scenario())

    assert done.status == "done"
    assert done.result == ANSWER
    assert done.problem is None


def test_a_problem_ends_the_job_as_failed():
    quota = Problem(type="quota_exhausted", title="נגמרה המכסה", status=503)

    async def finished():
        jobs = ExtractJobs()

        async def run(progress):
            return quota

        job = jobs.start("u1", run)
        await asyncio.sleep(0)
        return jobs.get(job.job_id)

    failed = asyncio.run(finished())

    assert (failed.status, failed.problem, failed.result) == ("failed", quota, None)


def test_a_job_that_breaks_is_stopped_not_lost(caplog):
    async def scenario():
        jobs = ExtractJobs()

        async def run(progress):
            raise RuntimeError("a bug, with 039337423 in its message")

        job = jobs.start("u1", run)
        await asyncio.sleep(0)
        return jobs.get(job.job_id)

    job = asyncio.run(scenario())

    assert (job.status, job.problem) == ("failed", STOPPED)
    assert "039337423" not in caplog.text  # only the error's type is logged


def test_a_job_is_found_by_its_id_alone():
    # Everyone sees everyone's records, so a job isn't kept to the user who started it.
    async def scenario():
        jobs = ExtractJobs()
        job = jobs.start("u1", lambda progress: answer_after(progress, asyncio.Event()))
        return jobs.get(job.job_id), jobs.get("no-such-job")

    found, unknown = asyncio.run(scenario())

    assert found.status == "running"
    assert unknown is None


def test_a_finished_job_is_forgotten_after_its_ttl():
    async def scenario():
        clock = Clock()
        jobs = ExtractJobs(finished_ttl_s=60, clock=clock)

        async def run(progress):
            return ANSWER

        job = jobs.start("u1", run)
        await asyncio.sleep(0)
        clock.now += 59
        kept = jobs.get(job.job_id)
        clock.now += 2
        return kept, jobs.get(job.job_id)

    kept, forgotten = asyncio.run(scenario())

    assert kept is not None
    assert forgotten is None


def test_a_running_job_is_never_forgotten():
    async def scenario():
        clock = Clock()
        jobs = ExtractJobs(finished_ttl_s=60, clock=clock)
        job = jobs.start("u1", lambda progress: answer_after(progress, asyncio.Event()))
        clock.now += 3600
        return jobs.get(job.job_id)

    assert asyncio.run(scenario()).status == "running"


def test_too_many_jobs_for_one_user_or_for_the_server_are_refused():
    async def scenario():
        jobs = ExtractJobs(max_running=3, max_running_per_user=2)
        gate = asyncio.Event()
        forever = lambda progress: answer_after(progress, gate)  # noqa: E731
        jobs.start("u1", forever)
        jobs.start("u1", forever)
        with pytest.raises(TooManyJobs) as for_user:
            jobs.start("u1", forever)
        jobs.start("u2", forever)
        with pytest.raises(TooManyJobs) as for_server:
            jobs.start("u3", forever)
        gate.set()
        await asyncio.sleep(0)
        jobs.start("u3", forever)  # once the others ended
        gate.set()
        return for_user.value.message, for_server.value.message

    assert asyncio.run(scenario()) == (BUSY_FOR_USER, BUSY)


def test_shutdown_waits_for_a_job_that_ends_in_time():
    async def scenario():
        jobs = ExtractJobs()

        async def run(progress):
            await asyncio.sleep(0.01)
            return ANSWER

        job = jobs.start("u1", run)
        await jobs.shutdown(grace_s=5)
        return jobs.get(job.job_id)

    assert asyncio.run(scenario()).status == "done"


def test_shutdown_stops_a_job_that_runs_too_long():
    async def scenario():
        jobs = ExtractJobs()
        job = jobs.start("u1", lambda progress: answer_after(progress, asyncio.Event()))
        await jobs.shutdown(grace_s=0.01)
        return jobs.get(job.job_id)

    stopped = asyncio.run(scenario())

    assert (stopped.status, stopped.problem) == ("failed", STOPPED)


def test_shutdown_with_no_jobs_returns_at_once():
    asyncio.run(ExtractJobs().shutdown(grace_s=60))
