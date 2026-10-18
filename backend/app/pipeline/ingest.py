"""Type/size checks, PDF/image -> pages. In memory only, nothing written to disk.

The file type comes from the first bytes, not the name, so a renamed file is
caught. Every image becomes a one-page PDF, so PDFs and photos share one render
path (and one rotation mechanism).

Owner: A
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import pymupdf

from app.extraction.provider import PageImage

# Longest side of the image sent to the model. An A4 scan comes out near 190 DPI,
# which read well in the spike; a 12MP phone photo is scaled down to the same size.
MAX_SIDE_PX = 2200
JPEG_QUALITY = 85
ROTATIONS = (0, 90, 180, 270)

# PyMuPDF is not thread-safe, so every render runs on this one thread: pages render
# one at a time while the model calls run concurrently, and the event loop is never
# blocked. A sample scan takes about 0.3s to render (48 sample pages: mean 0.3s, up
# to 1.3s under load), half decoding the embedded scan and half encoding the JPEG,
# far under a model call (4-9s). If renders ever queue up behind each other, render
# in a process pool instead.
_RENDER_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="render")

_SIGNATURES = {
    b"%PDF": "pdf",
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
}


class InvalidFile(Exception):
    """The file can't be processed. `message` is shown to the user, in Hebrew."""

    def __init__(self, filename: str, message: str) -> None:
        super().__init__(f"{filename}: {message}")
        self.filename = filename
        self.message = message


@dataclass(frozen=True)
class SourcePage:
    """One page of an uploaded file. Renders on demand, at any rotation.

    PyMuPDF is not thread-safe: from async code use render_async, which runs on
    the single render thread. Call render directly only from sync code and tests.
    """

    file_id: str
    filename: str
    page_number: int  # 1-based
    # The whole file as a PDF, shared by all its pages. repr=False: a log line or
    # traceback must never carry the document.
    _pdf: bytes = field(repr=False)

    def render(self, rotation: int = 0) -> PageImage:
        """Draw the page as a viewer shows it, then turned `rotation` degrees clockwise."""
        if rotation not in ROTATIONS:
            raise ValueError(f"rotation must be one of {ROTATIONS}, got {rotation}")
        with pymupdf.open(stream=self._pdf, filetype="pdf") as doc:
            page = doc[self.page_number - 1]
            # Add to the page's own /Rotate (scanners often store pages sideways and
            # rely on it), so rotation 0 means "as the viewer shows it".
            page.set_rotation((page.rotation + rotation) % 360)
            zoom = MAX_SIDE_PX / max(page.rect.width, page.rect.height)
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            jpeg = pixmap.tobytes("jpeg", jpg_quality=JPEG_QUALITY)
        return PageImage(
            file_id=self.file_id,
            filename=self.filename,
            page_number=self.page_number,
            rotation=rotation,
            jpeg=jpeg,
        )

    async def render_async(self, rotation: int = 0) -> PageImage:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_RENDER_THREAD, self.render, rotation)


def detect_type(data: bytes) -> str | None:
    for signature, kind in _SIGNATURES.items():
        if data.startswith(signature):
            return kind
    return None


def split_pages(
    file_id: str, filename: str, data: bytes, *, max_bytes: int, max_pages: int
) -> list[SourcePage]:
    """Check one uploaded file and return its pages. Raises InvalidFile.

    `max_pages` is per file; the service checks the total across a request.
    """
    if not data:
        raise InvalidFile(filename, "הקובץ ריק")
    if len(data) > max_bytes:
        raise InvalidFile(filename, f"הקובץ גדול מ־{max_bytes // 1_000_000}MB")
    kind = detect_type(data)
    if kind is None:
        raise InvalidFile(
            filename, "סוג קובץ לא נתמך. נתמכים PDF, JPG ו־PNG (צילום מאייפון: לשמור כ־JPG)"
        )

    try:
        with pymupdf.open(stream=data, filetype=kind) as doc:
            if doc.needs_pass:
                raise InvalidFile(filename, "הקובץ מוגן בסיסמה. יש לשמור אותו בלי סיסמה")
            pdf = data if kind == "pdf" else doc.convert_to_pdf()
            page_count = doc.page_count
    except RuntimeError as exc:  # includes pymupdf.FileDataError
        raise InvalidFile(filename, "לא ניתן לקרוא את הקובץ. ייתכן שהוא פגום") from exc

    if page_count == 0:
        raise InvalidFile(filename, "אין בקובץ עמודים")
    if page_count > max_pages:
        raise InvalidFile(filename, f"בקובץ {page_count} עמודים. המקסימום הוא {max_pages}")

    return [
        SourcePage(file_id=file_id, filename=filename, page_number=number, _pdf=pdf)
        for number in range(1, page_count + 1)
    ]
