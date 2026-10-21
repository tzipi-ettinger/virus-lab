"""Serve the built frontend (frontend/dist) from FastAPI (Dev-B plan 2.7).

On the live server the page and the API share one origin, so there is no CORS.
Only when STATIC_DIR is set, so in the Docker image;
in development Vite serves the page and forwards /api.

Owner: B
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.errors import ProblemError

# The page itself is tiny and names the hashed assets, so the browser must ask for
# it again after each deploy. The assets never change under the same name.
_NO_CACHE = {"Cache-Control": "no-cache"}
_API_DOCS = {"docs", "redoc", "openapi.json"}


def mount_spa(app: FastAPI, dist: Path) -> None:
    """Serve dist/assets, the files at the top of dist, and index.html for any other
    path, so a reload on /records/123 opens the app there. Add it after the routers:
    its catch-all route must come last."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR={dist} has no index.html. Build the frontend first.")
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/") or path in _API_DOCS:
            # A wrong API path is an API error, never the page. So are the API docs
            # when production turns them off.
            raise ProblemError(404, "not_found", "הכתובת לא נמצאה")
        file = (dist / path).resolve()
        if path and file.is_file() and file.is_relative_to(dist):
            return FileResponse(file)  # favicon.svg and the like
        return FileResponse(index, headers=_NO_CACHE)
