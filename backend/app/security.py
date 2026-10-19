"""Security headers on every response, the page's and the API's (Dev-B plan 2.7).

A plain ASGI middleware, not BaseHTTPMiddleware: it only adds headers to the
response start, so file and streaming responses go through untouched.

Owner: B
"""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

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
