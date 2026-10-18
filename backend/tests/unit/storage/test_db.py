import sqlite3

import pytest

from app.storage.db import SCHEMA_VERSION, SchemaVersionMismatch, connect, init_db

NOW = "2026-10-18T10:00:00Z"


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "data" / "test.db"
    init_db(path)
    return path


def insert_page(conn, page_id="p1"):
    conn.execute(
        "INSERT INTO page (id, source_filename, page_number, created_at) VALUES (?, ?, ?, ?)",
        (page_id, "part1.pdf", 1, NOW),
    )


def insert_record(conn, record_id="r1", page_id="p1", **values):
    row = {
        "id": record_id, "page_id": page_id, "commitment_idx": 0, "needs_review": 0,
        "created_at": NOW, "updated_at": NOW, **values,
    }
    cols = ", ".join(row)
    marks = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO record ({cols}) VALUES ({marks})", tuple(row.values()))


def test_init_creates_tables_and_sets_version(db_path):
    conn = connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    assert {"page", "page_image", "record", "record_field", "record_event"} <= tables
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_init_twice_keeps_data(db_path):
    with connect(db_path) as conn:
        insert_page(conn)

    init_db(db_path)

    assert connect(db_path).execute("SELECT COUNT(*) FROM page").fetchone()[0] == 1


def test_init_refuses_other_schema_version(db_path):
    with connect(db_path) as conn:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(SchemaVersionMismatch, match="Delete"):
        init_db(db_path)


def test_ids_keep_leading_zeros(db_path):
    with connect(db_path) as conn:
        insert_page(conn)
        insert_record(conn, national_id="011223344", commitment_number="0606")

    row = connect(db_path).execute("SELECT national_id, commitment_number FROM record").fetchone()

    assert (row["national_id"], row["commitment_number"]) == ("011223344", "0606")


def test_status_only_pending_or_approved(db_path):
    with connect(db_path) as conn:
        insert_page(conn)
        with pytest.raises(sqlite3.IntegrityError):
            insert_record(conn, status="done")


def test_deleting_page_deletes_its_records_and_image(db_path):
    with connect(db_path) as conn:
        insert_page(conn)
        insert_record(conn)
        conn.execute(
            "INSERT INTO page_image (page_id, mime, sha256, bytes) VALUES ('p1', 'image/jpeg', 'x', x'00')"
        )
        conn.execute(
            "INSERT INTO record_field (record_id, field, model_status, needs_review)"
            " VALUES ('r1', 'national_id', 'found', 0)"
        )

        conn.execute("DELETE FROM page WHERE id = 'p1'")

        for table in ("record", "record_field", "page_image"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_record_needs_existing_page(db_path):
    with connect(db_path) as conn:
        with pytest.raises(sqlite3.IntegrityError):
            insert_record(conn, page_id="missing")
