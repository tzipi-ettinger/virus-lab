"""scripts/seed_demo.py loads sample files as pending records, like an upload does."""

from datetime import UTC, datetime

import pymupdf
import pytest

from app.extraction.fake_provider import FakeProvider
from app.extraction.provider import PageImage, QuotaExhausted
from app.settings import Settings
from scripts.seed_demo import main

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
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


@pytest.fixture
def dana(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', 'x', 'דנה', %s)",
            (NOW,),
        )
    return db


def records(db):
    with db.connect() as conn:
        return conn.execute(
            "SELECT r.status, r.created_by, r.national_id, p.source_filename"
            " FROM record r JOIN page p ON p.id = r.page_id"
        ).fetchall()


def seed(db, *argv, provider=None):
    return main(
        list(argv), settings=SETTINGS, provider=provider or FakeProvider(), database_url=db.url
    )


def test_saves_every_form_in_the_folder_as_pending_records_of_the_user(dana, samples, capsys):
    assert seed(dana, str(samples), "--user", "dana") == 0

    saved = records(dana)
    assert saved
    assert {r["status"] for r in saved} == {"pending"}
    assert {r["created_by"] for r in saved} == {"u1"}
    assert {r["source_filename"] for r in saved} <= {"part1.pdf", "part2.pdf"}
    out = capsys.readouterr().out
    assert "part1.pdf: 2 pages" in out
    assert "notes.txt" not in out
    # Counts only, never a value from the records.
    assert not any(r["national_id"] and r["national_id"] in out for r in saved)


def test_takes_single_files_too(dana, samples):
    assert seed(dana, str(samples / "part2.pdf"), "--user", "dana") == 0

    assert {r["source_filename"] for r in records(dana)} == {"part2.pdf"}


def test_unknown_user_saves_nothing(dana, samples, capsys):
    assert seed(dana, str(samples), "--user", "nobody") == 1

    assert records(dana) == []
    assert "create_user" in capsys.readouterr().out


def test_missing_path_saves_nothing(dana, tmp_path):
    assert seed(dana, str(tmp_path / "nope"), "--user", "dana") == 1

    assert records(dana) == []


class NoQuota(FakeProvider):
    async def extract(self, page: PageImage):
        raise QuotaExhausted("המכסה היומית נגמרה")


def test_stops_when_the_quota_runs_out(dana, samples, capsys):
    assert seed(dana, str(samples), "--user", "dana", provider=NoQuota()) == 0

    out = capsys.readouterr().out
    assert "quota ran out" in out
    assert "part2.pdf" not in out  # never sent
    assert records(dana) == []
