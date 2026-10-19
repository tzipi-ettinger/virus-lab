"""The free Render instance is kept awake by pinging its own address (app/keep_alive.py)."""

import asyncio
import logging
import urllib.error

from app import keep_alive


def run_for(seconds: float, url: str, ping_fn) -> None:
    async def scenario() -> None:
        task = asyncio.create_task(keep_alive.keep_alive(url, 0.01, ping_fn))
        await asyncio.sleep(seconds)
        await keep_alive.stop_keep_alive(task)
        assert task.cancelled()

    asyncio.run(scenario())


def test_pings_the_url_again_and_again():
    calls = []
    run_for(0.2, "https://example.test/api/health", lambda url: calls.append(url) or 200)

    assert len(calls) >= 3
    assert set(calls) == {"https://example.test/api/health"}


def test_a_failed_ping_is_logged_and_the_loop_goes_on(caplog):
    calls = []

    def flaky(url: str) -> int:
        calls.append(url)
        if len(calls) == 1:
            raise urllib.error.HTTPError(url, 502, "Bad Gateway", None, None)
        if len(calls) == 2:
            raise TimeoutError
        return 200

    with caplog.at_level(logging.WARNING, logger="app.keep_alive"):
        run_for(0.2, "https://example.test/api/health", flaky)

    assert len(calls) >= 3
    failures = [r.getMessage() for r in caplog.records if "failed" in r.getMessage()]
    assert "(502)" in failures[0]
    assert "(TimeoutError)" in failures[1]


def test_no_url_no_task():
    async def scenario():
        return keep_alive.start_keep_alive("", 600)

    assert asyncio.run(scenario()) is None


def test_start_pings_health_on_the_base_url(monkeypatch):
    calls = []
    monkeypatch.setattr(keep_alive, "ping", lambda url: calls.append(url) or 200)

    async def scenario():
        task = keep_alive.start_keep_alive("https://virus-lab.example/", 0.01)
        await asyncio.sleep(0.1)
        await keep_alive.stop_keep_alive(task)

    asyncio.run(scenario())

    assert calls and set(calls) == {"https://virus-lab.example/api/health"}
