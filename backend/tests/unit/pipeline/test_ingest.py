import asyncio
import struct
import threading

import pymupdf
import pytest

from app.pipeline import ingest
from app.pipeline.ingest import (
    MAX_SIDE_PX,
    SAVE_MAX_SIDE_PX,
    InvalidFile,
    detect_type,
    split_pages,
    split_pages_async,
)

LIMITS = {"max_bytes": 20_000_000, "max_pages": 60}


def make_pdf(pages: int) -> bytes:
    with pymupdf.open() as doc:
        for number in range(pages):
            page = doc.new_page(width=595, height=842)  # A4 portrait, in points
            page.insert_text((72, 72), f"page {number + 1}")
        return doc.tobytes()


def make_image(kind: str, width: int = 400, height: int = 300) -> bytes:
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
    pixmap.clear_with(200)
    return pixmap.tobytes(kind)


def image_size(jpeg: bytes) -> tuple[int, int]:
    pixmap = pymupdf.Pixmap(jpeg)
    return pixmap.width, pixmap.height


@pytest.mark.parametrize(
    ("data", "kind"),
    [
        (b"%PDF-1.7 ...", "pdf"),
        (b"\xff\xd8\xff\xe0 ...", "jpeg"),
        (b"\x89PNG\r\n\x1a\n ...", "png"),
        (b"PK\x03\x04 a .docx", None),
        (b"\x00\x00\x00\x18ftypheic", None),
    ],
)
def test_detect_type_reads_the_first_bytes(data, kind):
    assert detect_type(data) == kind


def test_pdf_becomes_one_page_each():
    pages = split_pages("f1", "forms.pdf", make_pdf(3), **LIMITS)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert {page.file_id for page in pages} == {"f1"}
    assert {page.filename for page in pages} == {"forms.pdf"}


@pytest.mark.parametrize("kind", ["png", "jpeg"])
def test_image_becomes_one_page(kind):
    pages = split_pages("f1", f"photo.{kind}", make_image(kind), **LIMITS)

    assert len(pages) == 1
    assert pages[0].page_number == 1


def test_the_saved_image_is_smaller_and_turned_like_the_models():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    model = page.render(90)
    saved = page.render(90, max_side=SAVE_MAX_SIDE_PX, quality=ingest.SAVE_JPEG_QUALITY)

    width, height = image_size(saved.jpeg)
    assert max(width, height) == pytest.approx(SAVE_MAX_SIDE_PX, abs=2)
    assert width > height  # A4 portrait turned 90: landscape, like the model's image
    assert saved.rotation == model.rotation == 90
    assert len(saved.jpeg) < len(model.jpeg)


def test_render_returns_a_jpeg_scaled_to_the_longest_side():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    image = page.render()

    assert image.jpeg.startswith(b"\xff\xd8\xff")
    width, height = image_size(image.jpeg)
    assert max(width, height) == pytest.approx(MAX_SIDE_PX, abs=2)
    assert height > width  # A4 portrait stays portrait
    assert (image.file_id, image.filename, image.page_number, image.rotation) == (
        "f1",
        "forms.pdf",
        1,
        0,
    )


def test_render_rotates_clockwise():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    image = page.render(rotation=90)

    width, height = image_size(image.jpeg)
    assert width > height  # portrait turned on its side
    assert image.rotation == 90


def make_pdf_with_stored_rotation(rotation: int) -> bytes:
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.set_rotation(rotation)
        return doc.tobytes()


def test_render_keeps_the_rotation_stored_in_the_pdf():
    # Scanners often store a page sideways with /Rotate; rotation 0 = as a viewer shows it.
    page = split_pages("f1", "scan.pdf", make_pdf_with_stored_rotation(90), **LIMITS)[0]

    width, height = image_size(page.render().jpeg)

    assert width > height


def test_render_adds_to_the_stored_rotation():
    page = split_pages("f1", "scan.pdf", make_pdf_with_stored_rotation(90), **LIMITS)[0]

    width, height = image_size(page.render(rotation=90).jpeg)

    assert height > width  # 90 stored + 90 asked = upside down portrait


@pytest.mark.parametrize("rotation", [45, -90, 360])
def test_render_rejects_an_odd_rotation(rotation):
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    with pytest.raises(ValueError):
        page.render(rotation=rotation)


def make_marked_pdf(stored_rotation: int = 0) -> bytes:
    """A4 with one black rectangle off the center, so every turn moves it elsewhere."""
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.draw_rect(pymupdf.Rect(100, 150, 250, 220), color=(0, 0, 0), fill=(0, 0, 0))
        page.set_rotation(stored_rotation)
        return doc.tobytes()


def dark_box(jpeg: bytes) -> tuple[int, int, int, int]:
    """Where the dark pixels are, as (top, left, bottom, right) in 0-1000: a model's box."""
    pixmap = pymupdf.Pixmap(jpeg)
    width, n, samples = pixmap.width, pixmap.n, pixmap.samples
    dark = [
        (y, x)
        for y in range(pixmap.height)
        for x in range(width)
        if samples[(y * width + x) * n] < 100
    ]
    ys, xs = [y for y, _ in dark], [x for _, x in dark]
    return (
        min(ys) * 1000 // pixmap.height,
        min(xs) * 1000 // width,
        (max(ys) + 1) * 1000 // pixmap.height,
        (max(xs) + 1) * 1000 // width,
    )


def brightness(jpeg: bytes) -> float:
    samples = pymupdf.Pixmap(jpeg).samples
    return sum(samples) / len(samples)


@pytest.mark.parametrize("stored_rotation", [0, 90])
@pytest.mark.parametrize("rotation", ingest.ROTATIONS)
def test_a_crop_cuts_where_the_box_is_on_the_turned_image(stored_rotation, rotation):
    # The box comes from the model's image, turned: the crop must cut that same place.
    page = split_pages("f1", "scan.pdf", make_marked_pdf(stored_rotation), **LIMITS)[0]
    top, left, bottom, right = dark_box(page.render(rotation, max_side=300).jpeg)

    crop = page.render_crop(rotation, (top + 10, left + 10, bottom - 10, right - 10))
    corner = page.render_crop(rotation, (900, 900, 1000, 1000))

    assert brightness(crop.jpeg) < 40  # inside the rectangle: black
    assert brightness(corner.jpeg) > 240  # far from it: white
    assert crop.rotation == rotation


def test_a_crop_is_larger_than_the_models_image():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    whole = page.render_crop(0, (0, 0, 1000, 1000))

    width, height = image_size(whole.jpeg)
    assert max(width, height) == pytest.approx(ingest.CROP_SCALE * MAX_SIDE_PX, abs=2)
    assert height > width


@pytest.mark.parametrize(
    "box", [(10, 10, 10, 20), (10, 30, 20, 20), (0, 0, 1001, 50), (-1, 0, 5, 5)]
)
def test_a_crop_needs_a_rectangle_on_the_page(box):
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    with pytest.raises(ValueError):
        page.render_crop(0, box)


def test_a_crop_renders_on_the_render_thread():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    crop = asyncio.run(page.render_crop_async(90, (0, 0, 500, 500)))

    assert crop.jpeg.startswith(b"\xff\xd8")
    assert crop.rotation == 90


def test_repr_never_carries_the_document():
    page = split_pages("f1", "forms.pdf", make_pdf(1), **LIMITS)[0]

    assert len(repr(page)) < 200
    assert len(repr(page.render())) < 200


def test_password_protected_pdf_is_rejected():
    with pymupdf.open() as doc:
        doc.new_page()
        data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")

    with pytest.raises(InvalidFile) as error:
        split_pages("f1", "locked.pdf", data, **LIMITS)

    assert "סיסמה" in error.value.message


def test_a_large_photo_is_scaled_down():
    page = split_pages("f1", "photo.png", make_image("png", 4000, 3000), **LIMITS)[0]

    width, height = image_size(page.render().jpeg)

    assert max(width, height) == pytest.approx(MAX_SIDE_PX, abs=2)


@pytest.mark.parametrize(
    ("data", "limits", "message"),
    [
        (b"", LIMITS, "ריק"),
        (b"%PDF" + b"0" * 100, {"max_bytes": 50, "max_pages": 60}, "גדול"),
        (b"PK\x03\x04 a .docx", LIMITS, "לא נתמך"),
        (b"%PDF-1.7 this is not really a pdf", LIMITS, "לא ניתן לקרוא"),
    ],
)
def test_invalid_files_raise_a_hebrew_message(data, limits, message):
    with pytest.raises(InvalidFile) as error:
        split_pages("f1", "bad.pdf", data, **limits)

    assert message in error.value.message
    assert error.value.filename == "bad.pdf"


def test_too_many_pages():
    with pytest.raises(InvalidFile) as error:
        split_pages("f1", "big.pdf", make_pdf(3), max_bytes=20_000_000, max_pages=2)

    assert "3 עמודים" in error.value.message


# --- Images too large to decode safely. These headers claim a size the bytes don't
# hold, so no test decodes a real 400MP image.


def png_header(width: int, height: int) -> bytes:
    ihdr = struct.pack(">I4sII", 13, b"IHDR", width, height)
    return b"\x89PNG\r\n\x1a\n" + ihdr + b"\x00" * 8


def jpeg_header(width: int, height: int) -> bytes:
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof0 = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, height, width) + b"\x00" * 10
    return b"\xff\xd8" + app0 + sof0


@pytest.mark.parametrize("kind", ["png", "jpeg"])
def test_image_size_is_read_from_the_header(kind):
    assert ingest.image_size(make_image(kind, 400, 300), kind) == (400, 300)


@pytest.mark.parametrize(
    ("data", "kind"),
    [(png_header(20_000, 20_000), "png"), (jpeg_header(20_000, 20_000), "jpeg")],
    ids=["png", "jpeg"],
)
def test_a_huge_image_is_rejected_before_decoding(data, kind):
    assert ingest.image_size(data, kind) == (20_000, 20_000)

    with pytest.raises(InvalidFile) as error:
        split_pages("f1", f"photo.{kind}", data, **LIMITS)

    assert "גדולה מדי" in error.value.message


def test_a_huge_image_inside_a_pdf_is_rejected(monkeypatch):
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.insert_image(page.rect, stream=make_image("png", 400, 300))
        data = doc.tobytes()
    monkeypatch.setattr(ingest, "MAX_IMAGE_PIXELS", 400 * 300 - 1)

    with pytest.raises(InvalidFile) as error:
        split_pages("f1", "scan.pdf", data, **LIMITS)

    assert "גדולה מדי" in error.value.message


def test_the_page_count_is_checked_before_the_images(monkeypatch):
    # A PDF over the page limit is rejected without reading every page's images.
    with pymupdf.open() as doc:
        for _ in range(3):
            page = doc.new_page(width=595, height=842)
            page.insert_image(page.rect, stream=make_image("png", 400, 300))
        data = doc.tobytes()
    monkeypatch.setattr(ingest, "MAX_IMAGE_PIXELS", 1)

    with pytest.raises(InvalidFile) as error:
        split_pages("f1", "scan.pdf", data, max_bytes=20_000_000, max_pages=2)

    assert "3 עמודים" in error.value.message


def test_split_pages_async_runs_on_the_render_thread(monkeypatch):
    seen = []
    split = ingest.split_pages

    def spy(*args, **kwargs):
        seen.append(threading.current_thread().name)
        return split(*args, **kwargs)

    monkeypatch.setattr(ingest, "split_pages", spy)

    pages = asyncio.run(split_pages_async("f1", "forms.pdf", make_pdf(2), **LIMITS))

    assert [page.page_number for page in pages] == [1, 2]
    assert seen and seen[0].startswith("render")
