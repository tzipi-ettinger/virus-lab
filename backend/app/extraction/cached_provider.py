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
from collections.abc import Awaitable, Callable
from pathlib import Path

from pydantic import BaseModel, ValidationError

from app.extraction.provider import ExtractionProvider, NameReader, PageImage
from app.schemas.extraction import NameReading, RawExtraction

logger = logging.getLogger(__name__)

# Fixed, not configurable: the only place that is sure to be gitignored.
CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache" / "extraction"


class CachedProvider:
    def __init__(
        self,
        inner: ExtractionProvider,
        fingerprint: str,
        cache_dir: Path = CACHE_DIR,
        *,
        name_fingerprint: str | None = None,
    ) -> None:
        """`fingerprint` names what decides the answer besides the image: the model,
        the prompt, the schema. A new fingerprint starts from an empty cache.
        `name_fingerprint` is the same for read_name; without it, names aren't cached."""
        self._inner = inner
        self._fingerprint = fingerprint
        self._name_fingerprint = name_fingerprint
        self._dir = cache_dir
        self.hits = 0
        self.misses = 0

    async def extract(self, page: PageImage) -> RawExtraction:
        key = _key(self._fingerprint, page)
        return await self._cached(key, RawExtraction, lambda: self._inner.extract(page))

    async def read_name(self, crop: PageImage, *, deep: bool = False) -> NameReading:
        """For an inner provider that reads names (Gemini, the only one cached). The
        deep look at a crop is kept apart from the first one."""
        reader = self._inner
        if not isinstance(reader, NameReader):
            raise TypeError(f"{type(reader).__name__} does not read names")
        if self._name_fingerprint is None:
            return await reader.read_name(crop, deep=deep)
        fingerprint = f"{self._name_fingerprint}\ndeep" if deep else self._name_fingerprint
        key = _key(fingerprint, crop)
        return await self._cached(key, NameReading, lambda: reader.read_name(crop, deep=deep))

    async def _cached[T: BaseModel](
        self, key: str, schema: type[T], call: Callable[[], Awaitable[T]]
    ) -> T:
        path = self._dir / f"{key}.json"
        cached = await asyncio.to_thread(_read, path, schema)
        if cached is not None:
            self.hits += 1
            logger.info("cache hit %s", path.stem[:12])
            return cached
        self.misses += 1
        answer = await call()  # errors pass through, uncached
        try:
            await asyncio.to_thread(_write, path, answer.model_dump_json())
        except OSError as exc:
            logger.warning("cache not written: %s", type(exc).__name__)
        return answer


def _key(fingerprint: str, image: PageImage) -> str:
    # The rendered JPEG, not the file name: the same page under another name is a
    # hit, and a page turned another way (a different image) is a miss.
    digest = hashlib.sha256()
    digest.update(fingerprint.encode())
    digest.update(b"\0")
    digest.update(image.jpeg)
    return digest.hexdigest()


def _read[T: BaseModel](path: Path, schema: type[T]) -> T | None:
    try:
        return schema.model_validate_json(path.read_bytes())
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
