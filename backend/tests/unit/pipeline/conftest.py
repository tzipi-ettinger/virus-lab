import pymupdf
import pytest

from app.pipeline.ingest import SourcePage, split_pages


@pytest.fixture
def source_page() -> SourcePage:
    """One A4 page of a generated PDF (no sample data)."""
    with pymupdf.open() as doc:
        doc.new_page(width=595, height=842)
        data = doc.tobytes()
    return split_pages("f1", "forms.pdf", data, max_bytes=20_000_000, max_pages=60)[0]
