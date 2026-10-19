"""Hardening for the live server (Dev-B plan 2.7, B2.2): security headers on every
response, and no patient data in the server's logs.

Plain ASGI middleware, not BaseHTTPMiddleware: file and streaming responses go
through untouched.

Owner: B
"""

import logging

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import problem_response
from app.schemas.api import Problem

logger = logging.getLogger(__name__)

# Everything from our own origin. blob: and data: for the page images the preview
# draws. No framing (clickjacking), no plugins, no other site as a form target.
CSP = (
    "default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'; "
    "base-uri 'self'; form-action 'self'; object-src 'none'"
)
# Swagger UI loads its script from a CDN. These paths exist only in development.
_DOCS_PATHS = ("/docs", "/redoc")

_ALWAYS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}
# Only over HTTPS, so only on the live server: browsers then refuse plain HTTP.
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeaders:
    def __init__(self, app: ASGIApp, *, production: bool) -> None:
        self.app = app
        self.production = production

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _ALWAYS.items():
                    headers.setdefault(name, value)
                if not path.startswith(_DOCS_PATHS):
                    headers.setdefault("Content-Security-Policy", CSP)
                if self.production:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
                if path.startswith("/api/"):
                    # Answers hold patients' data: never in a browser or proxy cache.
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        await self.app(scope, receive, send_with_headers)


class HideUnexpectedErrors:
    """An error nobody handled answers a 500 problem+json, with the security headers,
    and logs its type and path only. Then it goes on up, as before: the server still
    sees it, and tests that expect it still get it. HideErrorText keeps its text out
    of the server's own log line.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except Exception as exc:
            logger.error(
                "unexpected %s on %s %s", type(exc).__name__, scope["method"], scope["path"]
            )
            if not started:  # otherwise the client already has part of an answer
                problem = Problem(
                    type="internal_error", title="משהו השתבש בשרת. אפשר לנסות שוב", status=500
                )
                await problem_response(problem)(scope, receive, send)
            raise


class HideErrorText(logging.Filter):
    """Uvicorn logs an unhandled error with its traceback and its text, and a database
    or validation error can quote the value it choked on (a national ID, a name).
    Keep the error's type only."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.exc_info and record.exc_info[0] is not None:
            record.msg = f"{str(record.msg).strip()}: %s"
            record.args = (record.exc_info[0].__name__,)
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return True


class DropQueryString(logging.Filter):
    """Uvicorn's access log writes the full URL, so a search would put a national ID
    or a name in the logs (GET /api/v1/records?q=...). Keep the path, drop the query."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn: (client, method, path with query, http version, status)
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            record.args = (*args[:2], args[2].split("?", 1)[0], *args[3:])
        return True


def keep_patient_data_out_of_server_logs() -> None:
    """Put the filters on uvicorn's loggers, once."""
    for name, kind in (("uvicorn.access", DropQueryString), ("uvicorn.error", HideErrorText)):
        log = logging.getLogger(name)
        if not any(isinstance(f, kind) for f in log.filters):
            log.addFilter(kind())
