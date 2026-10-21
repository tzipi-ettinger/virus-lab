"""scripts/wipe_data.py deletes every page, record and export (SPEC 11, D12)."""

from datetime import UTC, datetime

import pytest

from scripts.wipe_data import main

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
TABLES = ("page", "page_image", "record", "record_event", "export_log")


@pytest.fixture
def filled(db):
    with db.connect() as conn:
        for page_id, first in (("p1", None), ("p2", "p1")):
            conn.execute(
                "INSERT INTO page (id, file_id, source_filename, page_number, first_page_id,"
                " created_at) VALUES (%s, 'f1', 'a.pdf', %s, %s, %s)",
                (page_id, int(page_id[1]), first, NOW),
            )
            conn.execute(
                "INSERT INTO page_image (page_id, mime, sha256, bytes)"
                " VALUES (%s, 'image/jpeg', 'x', '\\x00')",
                (page_id,),
            )
        conn.execute(
            "INSERT INTO record (id, page_id, commitment_idx, needs_review, form_type, fields,"
            " central_numbers, issues, national_id, created_at, updated_at)"
            " VALUES ('r1', 'p1', 0, false, 'hmo_form', '{}', '[]', '[]', '011223344', %s, %s)",
            (NOW, NOW),
        )
        conn.execute(
            "INSERT INTO record_event (record_id, at, action) VALUES ('r1', %s, 'created')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO export_log (at, format, record_count) VALUES (%s, 'csv', 1)",
            (NOW,),
        )
    return db


def count(db, table):
    with db.connect() as conn:
        return conn.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"]


def test_deletes_pages_images_records_events_and_exports(filled, capsys):
    assert main(["--yes"], database_url=filled.url) == 0

    assert {table: count(filled, table) for table in TABLES} == dict.fromkeys(TABLES, 0)
    assert "Deleted 2 pages and 1 records" in capsys.readouterr().out


def test_asks_first_and_deletes_on_the_word(filled):
    assert main([], ask=lambda _prompt: "delete", database_url=filled.url) == 0

    assert count(filled, "record") == 0


@pytest.mark.parametrize("answer", ["", "y", "yes", "Delete it"])
def test_anything_else_deletes_nothing(filled, answer, capsys):
    assert main([], ask=lambda _prompt: answer, database_url=filled.url) == 1

    assert count(filled, "record") == 1
    assert count(filled, "page") == 2
    assert "Nothing deleted" in capsys.readouterr().out


def test_prints_no_values(filled, capsys):
    main(["--yes"], database_url=filled.url)

    assert "011223344" not in capsys.readouterr().out
