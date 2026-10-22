"""Type/size checks, PDF/image -> pages. In memory only, nothing written to disk.

The file type comes from the first bytes, not the name, so a renamed file is
caught. Every image becomes a one-page PDF, so PDFs and photos share one render
path (and one rotation mechanism).

Owner: A
"""

import asyncio
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import partial

import pymupdf

from app.extraction.provider import PageImage
from app.pipeline.split import SCALE, FormBox

# Longest side of the image sent to the model. An A4 scan comes out near 190 DPI,
# which read well in the spike; a 12MP phone photo is scaled down to the same size.
MAX_SIDE_PX = 2200
JPEG_QUALITY = 85
# The image saved with the records for the preview (D4; agreed with B in #15):
# smaller, since a person reads it on a screen with zoom, and it is kept.
SAVE_MAX_SIDE_PX = 1600
SAVE_JPEG_QUALITY = 80
# A form cut out of a page (several forms on one page, split.py) is cut from a
# larger drawing, so half a page still reaches MAX_SIDE_PX at the same detail.
CROP_MAX_SIDE_PX = 3300
CROP_JPEG_QUALITY = 90
ROTATIONS = (0, 90, 180, 270)
# A PNG of 126KB can hold a 108MP image, and rendering decodes all of it first. 100MP
# leaves room for a 48MP phone photo and a 600 DPI A4 scan (35MP).
MAX_IMAGE_PIXELS = 100_000_000

# PyMuPDF is not thread-safe, so every call into it from async code (split and
# render) runs on this one thread: pages render one at a time while the model calls
# run concurrently, and the event loop is never blocked. A sample scan takes about
# 0.3s to render (48 sample pages: mean 0.3s, up to 1.3s under load), half decoding
# the embedded scan and half encoding the JPEG, far under a model call (4-9s). If
# renders ever queue up behind each other, render in a process pool instead.
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
    # Where the page is in _pdf, when not at page_number: a form cut out of a page
    # (crop) is a one-page PDF of its own, and keeps the page number it came from.
    _pdf_index: int | None = field(default=None, repr=False)

    def render(
        self, rotation: int = 0, *, max_side: int = MAX_SIDE_PX, quality: int = JPEG_QUALITY
    ) -> PageImage:
        """Draw the page as a viewer shows it, then turned `rotation` degrees clockwise.

        Scaled so the longest side is `max_side` pixels. The defaults are the model's
        image; the saved image passes SAVE_MAX_SIDE_PX and SAVE_JPEG_QUALITY.
        """
        jpeg = self._pixmap(rotation, max_side).tobytes("jpeg", jpg_quality=quality)
        return PageImage(
            file_id=self.file_id,
            filename=self.filename,
            page_number=self.page_number,
            rotation=rotation,
            jpeg=jpeg,
        )

    async def render_async(
        self, rotation: int = 0, *, max_side: int = MAX_SIDE_PX, quality: int = JPEG_QUALITY
    ) -> PageImage:
        loop = asyncio.get_running_loop()
        render = partial(self.render, rotation, max_side=max_side, quality=quality)
        return await loop.run_in_executor(_RENDER_THREAD, render)

    def crop(self, rotation: int, box: FormBox, part: int) -> "SourcePage":
        """One form cut out of this page, as a page of its own.

        `box` is where the form is on the page turned `rotation` degrees (the image
        the model saw). The cut is drawn larger than the model's image, so the form
        keeps its detail once it is scaled up to MAX_SIDE_PX. `part` (from 1) goes
        into the file_id: the page table holds one row per file and page number.
        """
        pixmap = self._pixmap(rotation, CROP_MAX_SIDE_PX)
        width, height = pixmap.width, pixmap.height
        rect = pymupdf.IRect(
            box.left * width // SCALE,
            box.top * height // SCALE,
            box.right * width // SCALE,
            box.bottom * height // SCALE,
        )
        cut = pymupdf.Pixmap(pixmap.colorspace, rect, pixmap.alpha)
        cut.copy(pixmap, rect)
        jpeg = cut.tobytes("jpeg", jpg_quality=CROP_JPEG_QUALITY)
        with pymupdf.open(stream=jpeg, filetype="jpeg") as doc:
            pdf = doc.convert_to_pdf()
        return SourcePage(
            file_id=f"{self.file_id}-f{part}",
            filename=self.filename,
            page_number=self.page_number,
            _pdf=pdf,
            _pdf_index=0,
        )

    async def crop_async(self, rotation: int, box: FormBox, part: int) -> "SourcePage":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_RENDER_THREAD, self.crop, rotation, box, part)

    def _pixmap(self, rotation: int, max_side: int) -> pymupdf.Pixmap:
        if rotation not in ROTATIONS:
            raise ValueError(f"rotation must be one of {ROTATIONS}, got {rotation}")
        index = self.page_number - 1 if self._pdf_index is None else self._pdf_index
        with pymupdf.open(stream=self._pdf, filetype="pdf") as doc:
            page = doc[index]
            # Add to the page's own /Rotate (scanners often store pages sideways and
            # rely on it), so rotation 0 means "as the viewer shows it".
            page.set_rotation((page.rotation + rotation) % 360)
            zoom = max_side / max(page.rect.width, page.rect.height)
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))


def detect_type(data: bytes) -> str | None:
    for signature, kind in _SIGNATURES.items():
        if data.startswith(signature):
            return kind
    return None


def image_size(data: bytes, kind: str) -> tuple[int, int] | None:
    """(width, height) from a PNG or JPEG header, without decoding. None if not found."""
    if kind == "png":
        return struct.unpack(">II", data[16:24]) if len(data) >= 24 else None
    position = 2  # past the JPEG start marker
    while position + 9 <= len(data):
        if data[position] != 0xFF:
            return None
        marker = data[position + 1]
        if marker == 0xFF:  # fill byte
            position += 1
        elif 0xD0 <= marker <= 0xD7 or marker == 0x01:  # markers with no length
            position += 2
        elif 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # frame header
            height, width = struct.unpack(">HH", data[position + 5 : position + 9])
            return width, height
        else:
            position += 2 + struct.unpack(">H", data[position + 2 : position + 4])[0]
    return None


def _check_pixels(filename: str, width: int, height: int) -> None:
    if width * height > MAX_IMAGE_PIXELS:
        raise InvalidFile(
            filename,
            f"התמונה גדולה מדי ({width * height // 1_000_000} מגה־פיקסל). "
            f"המקסימום הוא {MAX_IMAGE_PIXELS // 1_000_000}",
        )


def split_pages(
    file_id: str, filename: str, data: bytes, *, max_bytes: int, max_pages: int
) -> list[SourcePage]:
    """Check one uploaded file and return its pages. Raises InvalidFile.

    `max_pages` is per file; the service checks the total across a request.
    From async code use split_pages_async (PyMuPDF is not thread-safe).
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
    # Before opening: converting an image to PDF already decodes it.
    if kind != "pdf" and (size := image_size(data, kind)):
        _check_pixels(filename, *size)

    try:
        with pymupdf.open(stream=data, filetype=kind) as doc:
            if doc.needs_pass:
                raise InvalidFile(filename, "הקובץ מוגן בסיסמה. יש לשמור אותו בלי סיסמה")
            page_count = doc.page_count
            # The page count first: the image check below reads every page.
            if page_count == 0:
                raise InvalidFile(filename, "אין בקובץ עמודים")
            if page_count > max_pages:
                raise InvalidFile(filename, f"בקובץ {page_count} עמודים. המקסימום הוא {max_pages}")
            if kind == "pdf":
                for page in doc:  # reads the image headers only, decodes nothing
                    for image in page.get_images(full=True):
                        _check_pixels(filename, image[2], image[3])
            pdf = data if kind == "pdf" else doc.convert_to_pdf()
    except RuntimeError as exc:  # includes pymupdf.FileDataError
        raise InvalidFile(filename, "לא ניתן לקרוא את הקובץ. ייתכן שהוא פגום") from exc

    return [
        SourcePage(file_id=file_id, filename=filename, page_number=number, _pdf=pdf)
        for number in range(1, page_count + 1)
    ]


async def split_pages_async(
    file_id: str, filename: str, data: bytes, *, max_bytes: int, max_pages: int
) -> list[SourcePage]:
    """split_pages on the render thread: two uploads at once never run PyMuPDF in
    parallel, and a photo's conversion to PDF doesn't block the event loop."""
    split = partial(split_pages, file_id, filename, data, max_bytes=max_bytes, max_pages=max_pages)
    return await asyncio.get_running_loop().run_in_executor(_RENDER_THREAD, split)
