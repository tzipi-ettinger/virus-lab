"""GET /api/health.

Also says which extraction provider is on, and whether the dev cache is in front
of it, so a deploy can be checked in a browser: a live server answering with "fake"
would serve fixtures that look like real readings, and one with the cache on would
keep patients' readings on its disk.

Owner: A
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.settings import Settings, get_settings

router = APIRouter()


@router.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "extraction_provider": settings.extraction_provider,
        # What get_provider does, not just the setting: the cache is only ever in
        # front of Gemini.
        "extraction_cache": settings.extraction_cache and settings.extraction_provider == "gemini",
    }
