"""Type/size checks, PDF/image -> pages. In memory only, nothing written to disk.

The file type comes from the first bytes, not the name, so a renamed file is
caught. Every image becomes a one-page PDF, so PDFs and photos share one render
path (and one rotation mechanism).

Owner: A
"""

import asyncio
import struct
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from functools import partial

import pymupdf

from app.extraction.provider import PageImage
from app.pipeline.boxes import SCALE, WHOLE, Box, as_box, turned

# Longest side of the image sent to the model. An A4 scan comes out near 190 DPI,
# which read well in the spike; a 12MP phone photo is scaled down to the same size.
MAX_SIDE_PX = 2200
JPEG_QUALITY = 85
# The image saved with the records for the preview (D4; agreed with B in #15):
# smaller, since a person reads it on a screen with zoom, and it is kept.
SAVE_MAX_SIDE_PX = 1600
SAVE_JPEG_QUALITY = 80
# The name's crop for its second read (render_crop, pipeline/names.py) is drawn from
# the page itself at twice the model image's scale: the handwriting gets more pixels
# than the whole page can give it, and up to the scan's own resolution, more detail too.
NAME_CROP_SCALE = 2
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
    # A form cut out of the page (crop) is the same page, drawn only inside `_box` of
    # it turned `_turn` degrees: every image of the form is drawn from the scan
    # itself, at the scan's own detail, and nothing is copied or drawn in advance.
    _turn: int = 0
    _box: Box = WHOLE

    def render(
        self, rotation: int = 0, *, max_side: int = MAX_SIDE_PX, quality: int = JPEG_QUALITY
    ) -> PageImage:
        """Draw the page as a viewer shows it, then turned `rotation` degrees clockwise.

        Scaled so the longest side is `max_side` pixels. The defaults are the model's
        image; the saved image passes SAVE_MAX_SIDE_PX and SAVE_JPEG_QUALITY.
        """
        jpeg = self._draw(rotation, max_side).tobytes("jpeg", jpg_quality=quality)
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

    def crop(self, rotation: int, box: Box, part: int) -> "SourcePage":
        """One form cut out of this page, as a page of its own.

        `box` is where the form is on the page turned `rotation` degrees (the image
        the model saw). `part` (from 1) goes into the file_id: the page table holds
        one row per file and page number. Draws nothing, so it costs nothing.
        """
        if rotation not in ROTATIONS:
            raise ValueError(f"rotation must be one of {ROTATIONS}, got {rotation}")
        if self._box != WHOLE:
            raise ValueError("a form cut out of a page is not cut again")
        return replace(self, file_id=f"{self.file_id}-f{part}", _turn=rotation, _box=box)

    def render_crop(
        self, rotation: int, box: tuple[int, int, int, int], *, scale: float = NAME_CROP_SCALE
    ) -> PageImage:
        """Part of the page as render(rotation) draws it, `scale` times larger.

        `box` is (top, left, bottom, right) in 0-1000 of that image: the model's
        box_2d format, so a box read on the model's image cuts the same place.
        Unlike crop(), the result is an image for the model, not a page of its own.
        """
        part = as_box(box)
        if part is None:
            raise ValueError(f"box must be a rectangle within 0-1000, got {box}")
        jpeg = self._draw(rotation, scale * MAX_SIDE_PX, part).tobytes(
            "jpeg", jpg_quality=JPEG_QUALITY
        )
        return PageImage(
            file_id=self.file_id,
            filename=self.filename,
            page_number=self.page_number,
            rotation=rotation,
            jpeg=jpeg,
        )

    async def render_crop_async(
        self, rotation: int, box: tuple[int, int, int, int], *, scale: float = NAME_CROP_SCALE
    ) -> PageImage:
        loop = asyncio.get_running_loop()
        crop = partial(self.render_crop, rotation, box, scale=scale)
        return await loop.run_in_executor(_RENDER_THREAD, crop)

    def _draw(self, rotation: int, longest: float, part: Box = WHOLE) -> pymupdf.Pixmap:
        """`part` of the page turned `rotation` degrees, at the scale that draws the
        whole page `longest` pixels on its longest side."""
        if rotation not in ROTATIONS:
            raise ValueError(f"rotation must be one of {ROTATIONS}, got {rotation}")
        with pymupdf.open(stream=self._pdf, filetype="pdf") as doc:
            page = doc[self.page_number - 1]
            # Add to the page's own /Rotate (scanners often store pages sideways and
            # rely on it), so rotation 0 means "as the viewer shows it".
            page.set_rotation((page.rotation + self._turn + rotation) % 360)
            # As turned: the clip is in the same coordinates. All of it, but for a form
            # cut out of it, which turns with the page.
            whole = _within(page.rect, turned(self._box, rotation))
            zoom = longest / max(whole.width, whole.height)
            return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=_within(whole, part))


def _within(rect: pymupdf.Rect, box: Box) -> pymupdf.Rect:
    """The part of `rect` that `box` marks, in 0-1000 of it."""
    return pymupdf.Rect(
        rect.x0 + box.left / SCALE * rect.width,
        rect.y0 + box.top / SCALE * rect.height,
        rect.x0 + box.right / SCALE * rect.width,
        rect.y0 + box.bottom / SCALE * rect.height,
    )


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
