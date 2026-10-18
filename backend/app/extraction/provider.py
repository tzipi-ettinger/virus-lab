"""Protocol: extract(page) -> RawExtraction.

Every provider (Gemini, fake, cached) takes one rendered page and returns what
the model read. The pipeline only knows this interface, so swapping the model
is a settings change.

Owner: A
"""

from dataclasses import dataclass
from typing import Protocol

from app.schemas.extraction import RawExtraction


@dataclass(frozen=True)
class PageImage:
    """One page as the model sees it: a JPEG, already rotated by `rotation` degrees."""

    file_id: str
    filename: str
    page_number: int  # 1-based
    rotation: int  # clockwise degrees applied before rendering
    jpeg: bytes


class ExtractionProvider(Protocol):
    async def extract(self, page: PageImage) -> RawExtraction: ...


class ProviderError(Exception):
    """The page could not be read. `message` is shown to the user, in Hebrew."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class QuotaExhausted(ProviderError):
    """The daily quota is used up: every further call would fail, so stop the batch."""
