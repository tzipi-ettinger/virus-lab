"""Serves tests/fixtures, no network. B develops against this.

Every page gets one fixture, picked from the file name and the page number, so a
PDF of any length shows a realistic mix: clean pages, rotated pages, silent model
mistakes and a failed call. The same page of the same file always gets the same
fixture; different files usually start at different fixtures (the start comes from a
hash of the name, so two names share it about once in len(fixtures)), so a multi-file
upload doesn't look like a batch of duplicates. No quota, no API key.

Owner: A
"""

import asyncio
import hashlib
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

    def fixture_index(self, page: PageImage) -> int:
        # sha256, not hash() (changes between runs) or crc32 (linear: names that differ
        # in one character, like scan_1.pdf and scan_2.pdf, can land on the same offset).
        digest = hashlib.sha256(page.filename.encode("utf-8")).digest()
        offset = int.from_bytes(digest[:4], "big")
        return (offset + page.page_number - 1) % len(self._fixtures)

    async def extract(self, page: PageImage) -> RawExtraction:
        if self._delay_s:
            await asyncio.sleep(self._delay_s)
        fixture = self._fixtures[self.fixture_index(page)]
        if isinstance(fixture, str):
            raise ProviderError(fixture)  # a new instance each time, so tracebacks don't pile up
        # The fixture's rotation is what the unrotated page needs. Answer for the
        # rotation already applied, the way the real model sees a turned image.
        needed = (fixture.page_rotation_degrees - page.rotation) % 360
        # deep=True: callers get their own fields, so a change never leaks into later pages.
        return fixture.model_copy(update={"page_rotation_degrees": needed}, deep=True)


def _load(path: Path) -> RawExtraction | str:
    """A fixture, or the Hebrew message of a ProviderError to raise."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if "provider_error" in data:
        return data["provider_error"]
    return RawExtraction.model_validate(data)
