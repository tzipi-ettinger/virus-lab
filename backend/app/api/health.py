"""GET /api/health.

Also says which extraction provider is on, so a deploy can be checked in a browser:
a live server answering with "fake" would serve fixtures that look like real readings.

Owner: A
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.settings import Settings, get_settings

router = APIRouter()


@router.get("/api/health")
def health(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    return {"status": "ok", "extraction_provider": settings.extraction_provider}
