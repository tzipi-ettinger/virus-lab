"""One password for the whole site (D22): HTTP Basic, so the browser asks for it
itself and sends it with every request after that, the page's own fetches too.

Every path needs it except /api/health: Render's health check and the keep-alive
ping call it without one, and it holds no patient data. Off when SITE_PASSWORD
is empty (development and tests).

Owner: A
"""

import base64
import binascii
import secrets

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.errors import problem_response
from app.schemas.api import Problem

OPEN_PATHS = frozenset({"/api/health"})
# charset: a Hebrew password reaches the server as UTF-8, not Latin-1.
_CHALLENGE = {"WWW-Authenticate": 'Basic realm="virus-lab", charset="UTF-8"'}
_UNAUTHORIZED = Problem(type="unauthorized", title="צריך סיסמה כדי להיכנס לאתר", status=401)


class SitePassword:
    def __init__(self, app: ASGIApp, *, username: str, password: str) -> None:
        self.app = app
        self._username = username.encode()
        self._password = password.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in OPEN_PATHS:
            await self.app(scope, receive, send)
            return
        if self._allowed(Headers(scope=scope).get("authorization", "")):
            await self.app(scope, receive, send)
            return
        await problem_response(_UNAUTHORIZED, _CHALLENGE)(scope, receive, send)

    def _allowed(self, header: str) -> bool:
        scheme, _, encoded = header.partition(" ")
        if scheme.lower() != "basic":
            return False
        try:
            decoded = base64.b64decode(encoded.strip(), validate=True)
        except (binascii.Error, ValueError):
            return False
        username, colon, password = decoded.partition(b":")
        # Both compared, always: stopping at a wrong username would tell it apart by time.
        right_username = secrets.compare_digest(username, self._username)
        right_password = secrets.compare_digest(password, self._password)
        return bool(colon) and right_username and right_password
