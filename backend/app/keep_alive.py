"""Keep the free Render instance awake (Dev-B plan 2.7, D3).

Render puts a free web service to sleep after 15 minutes with no request from
outside, and the next visit then waits about a minute. This background task asks
the server's own public address for /api/health every KEEP_ALIVE_INTERVAL_S
seconds. The request goes out to the internet and back in through Render, so it
counts as outside traffic, and Render's access log shows it.

If the server crashes or restarts, the loop starts again with it. Only a server
that is already asleep stays asleep until the next visit.

Owner: B
"""

import asyncio
import contextlib
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable

logger = logging.getLogger(__name__)

TIMEOUT_S = 10

Ping = Callable[[str], int]


def ping(url: str) -> int:
    """GET the URL and return the HTTP status. Raises on a network error or a 4xx/5xx."""
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:
        return response.status


async def keep_alive(url: str, interval_s: float, ping_fn: Ping | None = None) -> None:
    """Ping the URL every interval_s seconds until cancelled. A failure is logged, never raised."""
    ping_fn = ping_fn or ping
    while True:
        await asyncio.sleep(interval_s)
        started = time.monotonic()
        try:
            await asyncio.to_thread(ping_fn, url)
        except Exception as exc:  # any failure: log it and try again next time
            # The status and the time only: the URL is our own, but keep logs plain.
            status = exc.code if isinstance(exc, urllib.error.HTTPError) else type(exc).__name__
            logger.warning(
                "keep-alive ping failed (%s) after %.1fs", status, time.monotonic() - started
            )


def start_keep_alive(base_url: str, interval_s: float) -> asyncio.Task[None] | None:
    """Start the loop on {base_url}/api/health, or do nothing when base_url is empty."""
    if not base_url:
        return None
    url = base_url.rstrip("/") + "/api/health"
    logger.warning("keep-alive is on: %s every %ss", url, interval_s)
    return asyncio.create_task(keep_alive(url, interval_s), name="keep-alive")


async def stop_keep_alive(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
