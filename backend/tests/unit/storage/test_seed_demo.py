"""scripts/seed_demo.py loads sample files as pending records, like an upload does."""

import pymupdf
import pytest

from app.extraction.fake_provider import FakeProvider
from app.extraction.provider import PageImage, QuotaExhausted
from app.settings import Settings
from scripts.seed_demo import main

SETTINGS = Settings(_env_file=None, database_url="")


def make_pdf(pages: int) -> bytes:
    with pymupdf.open() as doc:
        for _ in range(pages):
            doc.new_page(width=595, height=842)
        return doc.tobytes()


@pytest.fixture
def samples(tmp_path):
    folder = tmp_path / "samples"
    folder.mkdir()
    (folder / "part1.pdf").write_bytes(make_pdf(2))
    (folder / "part2.pdf").write_bytes(make_pdf(1))
    (folder / "notes.txt").write_text("not a form", encoding="utf-8")
    return folder


def records(db):
    with db.connect() as conn:
        return conn.execute(
            "SELECT r.status, r.national_id, p.source_filename"
            " FROM record r JOIN page p ON p.id = r.page_id"
        ).fetchall()


def seed(db, *argv, provider=None):
    return main(
        list(argv), settings=SETTINGS, provider=provider or FakeProvider(), database_url=db.url
    )


def test_saves_every_form_in_the_folder_as_pending_records(db, samples, capsys):
    assert seed(db, str(samples)) == 0

    saved = records(db)
    assert saved
    assert {r["status"] for r in saved} == {"pending"}
    assert {r["source_filename"] for r in saved} <= {"part1.pdf", "part2.pdf"}
    out = capsys.readouterr().out
    assert "part1.pdf: 2 pages" in out
    assert "notes.txt" not in out
    # Counts only, never a value from the records.
    assert not any(r["national_id"] and r["national_id"] in out for r in saved)


def test_takes_single_files_too(db, samples):
    assert seed(db, str(samples / "part2.pdf")) == 0

    assert {r["source_filename"] for r in records(db)} == {"part2.pdf"}


def test_missing_path_saves_nothing(db, tmp_path):
    assert seed(db, str(tmp_path / "nope")) == 1

    assert records(db) == []


class NoQuota(FakeProvider):
    async def extract(self, page: PageImage):
        raise QuotaExhausted("המכסה היומית נגמרה")


def test_stops_when_the_quota_runs_out(db, samples, capsys):
    assert seed(db, str(samples), provider=NoQuota()) == 0

    out = capsys.readouterr().out
    assert "quota ran out" in out
    assert "part2.pdf" not in out  # never sent
    assert records(db) == []
