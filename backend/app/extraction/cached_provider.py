"""Dev-only cache to save quota. Off by default; cache dir is gitignored.

Wraps a provider: a page the model already read, with the same model and prompt,
is answered from disk instead of a new call. That is what makes the measurement
on the ground truth affordable on 20 requests a day: running it again after a
change elsewhere costs nothing, and a prompt change re-reads the pages, since the
prompt is part of the key.

Only successful readings are kept. An error is never cached, so the next run
tries the page again. Reading or writing the cache never fails a page: a broken
or unreadable entry is a miss, and a write that fails is only logged.

The files hold what the model read, names and IDs included, so they live only
under backend/.cache/ (gitignored), and the cache is for the challenge's sample
files only (SPEC 11.1). Logs carry a short key prefix, never the reading.

Owner: A
"""

import asyncio
import hashlib
import logging
import os
from pathlib import Path

from pydantic import ValidationError

from app.extraction.provider import ExtractionProvider, PageImage
from app.schemas.extraction import RawExtraction

logger = logging.getLogger(__name__)

# Fixed, not configurable: the only place that is sure to be gitignored.
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "extraction"


class CachedProvider:
    def __init__(
        self, inner: ExtractionProvider, fingerprint: str, cache_dir: Path = CACHE_DIR
    ) -> None:
        """`fingerprint` names what decides the answer besides the image: the model,
        the prompt, the schema. A new fingerprint starts from an empty cache."""
        self._inner = inner
        self._fingerprint = fingerprint
        self._dir = cache_dir
        self.hits = 0
        self.misses = 0

    async def extract(self, page: PageImage) -> RawExtraction:
        path = self._dir / f"{self._key(page)}.json"
        cached = await asyncio.to_thread(_read, path)
        if cached is not None:
            self.hits += 1
            logger.info("cache hit %s", path.stem[:12])
            return cached
        self.misses += 1
        extraction = await self._inner.extract(page)  # errors pass through, uncached
        try:
            await asyncio.to_thread(_write, path, extraction.model_dump_json())
        except OSError as exc:
            logger.warning("cache not written: %s", type(exc).__name__)
        return extraction

    def _key(self, page: PageImage) -> str:
        # The rendered JPEG, not the file name: the same page under another name is a
        # hit, and a page turned another way (a different image) is a miss.
        digest = hashlib.sha256()
        digest.update(self._fingerprint.encode())
        digest.update(b"\0")
        digest.update(page.jpeg)
        return digest.hexdigest()


def _read(path: Path) -> RawExtraction | None:
    try:
        return RawExtraction.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        return None
    except (OSError, ValidationError) as exc:  # broken or from an older schema: read again
        logger.warning("cache entry ignored: %s", type(exc).__name__)
        return None


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Whole or not at all: two uploads of the same page never leave half a file.
    temp = path.with_suffix(f".{os.getpid()}.{id(text)}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
