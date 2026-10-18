"""Serves tests/fixtures, no network. B develops against this.

Page N of any upload gets the Nth fixture (sorted by name), cycling, so a PDF
of any length shows a realistic mix: clean pages, rotated pages, silent model
mistakes and a failed call. No quota, no API key.

Owner: A
"""

import asyncio
import json
from pathlib import Path

from app.extraction.provider import PageImage, ProviderError
from app.schemas.extraction import RawExtraction

FIXTURES_DIR = Path(__file__).parents[2] / "tests" / "fixtures" / "extraction"


class FakeProvider:
    def __init__(self, fixtures_dir: Path = FIXTURES_DIR, *, delay_s: float = 0.0) -> None:
        self._fixtures = [_load(path) for path in sorted(fixtures_dir.glob("*.json"))]
        if not self._fixtures:
            raise ValueError(f"no fixtures in {fixtures_dir}")
        self._delay_s = delay_s  # set it to see the upload progress in the UI

    async def extract(self, page: PageImage) -> RawExtraction:
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        fixture = self._fixtures[(page.page_number - 1) % len(self._fixtures)]
        if isinstance(fixture, ProviderError):
            raise fixture
        # The fixture's rotation is what the unrotated page needs. Answer for the
        # rotation already applied, the way the real model sees a turned image.
        needed = (fixture.page_rotation_degrees - page.rotation) % 360
        return fixture.model_copy(update={"page_rotation_degrees": needed})


def _load(path: Path) -> RawExtraction | ProviderError:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "provider_error" in data:
        return ProviderError(data["provider_error"])
    return RawExtraction.model_validate(data)
