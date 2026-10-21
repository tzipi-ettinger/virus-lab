"""GET /api/health.

Also says which extraction provider is on, how many Gemini keys it has, and
whether the dev cache is in front of it, so a deploy can be checked in a browser:
a live server answering with "fake" would serve fixtures that look like real
readings, and one with the cache on would keep patients' readings on its disk.
The number of keys, never a key: a server showing 1 has not picked up
GEMINI_API_KEYS.

Open without the site password (app/site_password.py): Render's health check
and the keep-alive ping call it without one.

Owner: A
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.settings import Settings, get_settings

router = APIRouter()


@router.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str | bool | int]:
    return {
        "status": "ok",
        "extraction_provider": settings.extraction_provider,
        # What get_provider does, not just the setting: the cache is only ever in
        # front of Gemini.
        "extraction_cache": settings.extraction_cache and settings.extraction_provider == "gemini",
        # Only Gemini reads with keys; fake has none, whatever .env holds.
        "gemini_keys": len(settings.gemini_keys())
        if settings.extraction_provider == "gemini"
        else 0,
        # Whether the site asks for SITE_PASSWORD, never the password: a live server
        # showing false is open to anyone with the link.
        "site_password": bool(settings.site_password.get_secret_value()),
    }
