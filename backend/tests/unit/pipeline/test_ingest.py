import pymupdf
import pytest

from app.pipeline.ingest import MAX_SIDE_PX, InvalidFile, detect_type, split_pages

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
