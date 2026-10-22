from pathlib import Path

import psycopg
import pytest

from app.storage.db import SCHEMA_VERSION, SchemaVersionMismatch, init_db, open_pool

NOW = "2026-10-18T10:00:00Z"
SCHEMA_V1 = Path(__file__).parents[2] / "fixtures" / "schema_v1.sql"
SCHEMA_V2 = Path(__file__).parents[2] / "fixtures" / "schema_v2.sql"
TABLES = {
    "schema_meta",
    "users",
    "sessions",
    "page",
    "page_image",
    "record",
    "record_event",
    "export_log",
}


def insert_user(conn, user_id="u1"):
    conn.execute(
        "INSERT INTO users (id, username, password_hash, display_name, created_at)"
        " VALUES (%s, %s, 'x', 'Test', %s) ON CONFLICT DO NOTHING",
        (user_id, user_id, NOW),
    )


def insert_page(conn, page_id="p1", page_number=1, first_page_id=None):
    insert_user(conn)
    conn.execute(
        "INSERT INTO page (id, file_id, source_filename, page_number, first_page_id,"
        " created_at, created_by) VALUES (%s, 'f1', 'part1.pdf', %s, %s, %s, 'u1')",
        (page_id, page_number, first_page_id, NOW),
    )


def insert_record(conn, record_id="r1", page_id="p1", **values):
    row = {
        "id": record_id,
        "page_id": page_id,
        "commitment_idx": 0,
        "needs_review": False,
        "form_type": "unknown",
        "fields": "{}",
        "central_numbers": "[]",
        "issues": "[]",
        "created_at": NOW,
        "created_by": "u1",
        "updated_at": NOW,
        **values,
    }
    cols = ", ".join(row)
    marks = ", ".join("%s" for _ in row)
    conn.execute(f"INSERT INTO record ({cols}) VALUES ({marks})", tuple(row.values()))


async def init_again(db):
    async with await db.connect_async() as conn:
        await init_db(conn)


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]


def tables(conn):
    return {
        row["tablename"]
        for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }


def columns(conn, table):
    return {
        row["column_name"]
        for row in conn.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)
        )
    }


def test_init_creates_tables_and_sets_version(db):
    with db.connect() as conn:
        version = conn.execute("SELECT version FROM schema_meta").fetchone()["version"]
        assert tables(conn) == TABLES
    assert version == SCHEMA_VERSION


def test_who_did_it_is_kept(db):
    # Sign-in is back (22.10): every page, record, event and export names its user.
    with db.connect() as conn:
        assert "created_by" in columns(conn, "page")
        assert {"created_by", "approved_by"} <= columns(conn, "record")
        assert "user_id" in columns(conn, "record_event")
        assert "user_id" in columns(conn, "export_log")


def test_init_twice_keeps_data(db):
    with db.connect() as conn:
        insert_page(conn)

    db.run(init_again(db))

    with db.connect() as conn:
        assert count(conn, "page") == 1
        assert count(conn, "schema_meta") == 1


def test_init_refuses_other_schema_version(db):
    with db.connect() as conn:
        conn.execute("UPDATE schema_meta SET version = version + 1")
    try:
        with pytest.raises(SchemaVersionMismatch, match="docker compose down -v"):
            db.run(init_again(db))
    finally:
        with db.connect() as conn:
            conn.execute("UPDATE schema_meta SET version = %s", (SCHEMA_VERSION,))


@pytest.fixture
def db_v1(db):
    """The test database at schema version 1, as the live one was before 21.10, with
    a user, a page, a record, an event, an export and a session. Put back at the
    current version afterwards, for the other tests."""
    with db.connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(SCHEMA_V1.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_meta (version) VALUES (1)")
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'dana', 'x', 'Dana', %s)",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at)"
            " VALUES ('h', 'u1', %s, %s, %s)",
            (NOW, NOW, NOW),
        )
        conn.execute(
            "INSERT INTO page (id, file_id, source_filename, page_number, created_at, created_by)"
            " VALUES ('p1', 'f1', 'part1.pdf', 1, %s, 'u1')",
            (NOW,),
        )
        insert_record(
            conn,
            national_id="011223344",
            status="approved",
            approved_at=NOW,
            created_by="u1",
            approved_by="u1",
        )
        conn.execute(
            "INSERT INTO record_event (record_id, at, user_id, action)"
            " VALUES ('r1', %s, 'u1', 'approved')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO export_log (at, user_id, format, record_count)"
            " VALUES (%s, 'u1', 'csv', 1)",
            (NOW,),
        )
    yield db
    with db.connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    db.run(init_again(db))


def test_init_upgrades_a_version_1_database_and_keeps_its_records(db_v1):
    db_v1.run(init_again(db_v1))

    # 1 -> 2 drops the users, so 2 -> 3 gives everything to the legacy user.
    with db_v1.connect() as conn:
        assert conn.execute("SELECT version FROM schema_meta").fetchone()["version"] == 3
        assert tables(conn) == TABLES
        record = conn.execute(
            "SELECT id, national_id, status, created_by, approved_by FROM record"
        ).fetchone()
        assert record == {
            "id": "r1",
            "national_id": "011223344",
            "status": "approved",
            "created_by": "legacy",
            "approved_by": "legacy",
        }
        assert count(conn, "page") == 1
        assert count(conn, "record_event") == 1
        assert count(conn, "export_log") == 1


@pytest.fixture
def db_v2(db):
    """The test database at schema version 2, as the live one is (21.10-22.10, no
    sign-in), with an approved record, a pending one, an event and an export.
    Put back at the current version afterwards, for the other tests."""
    with db.connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
        conn.execute(SCHEMA_V2.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_meta (version) VALUES (2)")
        conn.execute(
            "INSERT INTO page (id, file_id, source_filename, page_number, created_at)"
            " VALUES ('p1', 'f1', 'part1.pdf', 1, %s)",
            (NOW,),
        )
        for record_id, idx, approved_at in (("r1", 0, NOW), ("r2", 1, None)):
            conn.execute(
                "INSERT INTO record (id, page_id, commitment_idx, needs_review, form_type,"
                " fields, central_numbers, issues, created_at, updated_at, status, approved_at)"
                " VALUES (%s, 'p1', %s, FALSE, 'unknown', '{}', '[]', '[]', %s, %s, %s, %s)",
                (record_id, idx, NOW, NOW, "approved" if approved_at else "pending", approved_at),
            )
        conn.execute(
            "INSERT INTO record_event (record_id, at, action) VALUES ('r1', %s, 'approved')",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO export_log (at, format, record_count) VALUES (%s, 'csv', 1)", (NOW,)
        )
    yield db
    with db.connect() as conn:
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    db.run(init_again(db))


def test_init_upgrades_the_live_version_2_database_and_keeps_its_records(db_v2):
    db_v2.run(init_again(db_v2))

    with db_v2.connect() as conn:
        assert conn.execute("SELECT version FROM schema_meta").fetchone()["version"] == 3
        assert tables(conn) == TABLES
        rows = conn.execute("SELECT id, created_by, approved_by FROM record ORDER BY id").fetchall()
        assert rows == [
            {"id": "r1", "created_by": "legacy", "approved_by": "legacy"},
            {"id": "r2", "created_by": "legacy", "approved_by": None},
        ]
        assert conn.execute("SELECT created_by FROM page").fetchone()["created_by"] == "legacy"
        assert conn.execute("SELECT user_id FROM record_event").fetchone()["user_id"] == "legacy"
        assert conn.execute("SELECT user_id FROM export_log").fetchone()["user_id"] == "legacy"
        legacy = conn.execute(
            "SELECT is_active, password_hash FROM users WHERE id = 'legacy'"
        ).fetchone()
        assert legacy == {"is_active": False, "password_hash": "!"}


def test_fresh_and_upgraded_databases_have_the_same_columns(db_v2):
    db_v2.run(init_again(db_v2))
    with db_v2.connect() as conn:
        upgraded = {table: columns(conn, table) for table in TABLES}
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    db_v2.run(init_again(db_v2))
    with db_v2.connect() as conn:
        assert {table: columns(conn, table) for table in TABLES} == upgraded


def test_open_pool_checks_schema_and_gives_dict_rows(db):
    async def first_version():
        pool = await open_pool(db.url, max_size=1)
        try:
            async with pool.connection() as conn:
                cur = await conn.execute("SELECT version FROM schema_meta")
                return await cur.fetchone()
        finally:
            await pool.close()

    assert db.run(first_version()) == {"version": SCHEMA_VERSION}


def test_open_pool_replaces_a_connection_the_database_cut(db):
    # A database restart or failover ends the pool's idle connections. The next
    # request must get a working one, not the dead one and a 500 (22.10).
    async def after_the_cut():
        pool = await open_pool(db.url, max_size=1)
        try:
            async with pool.connection() as conn:
                cur = await conn.execute("SELECT pg_backend_pid() AS pid")
                pid = (await cur.fetchone())["pid"]
            with db.connect() as admin:
                admin.execute("SELECT pg_terminate_backend(%s)", (pid,))
            async with pool.connection() as conn:
                cur = await conn.execute("SELECT 1 AS ok")
                return await cur.fetchone()
        finally:
            await pool.close()

    assert db.run(after_the_cut()) == {"ok": 1}


def test_ids_keep_leading_zeros(db):
    with db.connect() as conn:
        insert_page(conn)
        insert_record(conn, national_id="011223344", commitment_number="0606")

        row = conn.execute("SELECT national_id, commitment_number FROM record").fetchone()

    assert row == {"national_id": "011223344", "commitment_number": "0606"}


def test_status_only_pending_or_approved(db):
    with db.connect() as conn:
        insert_page(conn)
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_record(conn, status="done")


def test_record_needs_existing_page(db):
    with db.connect() as conn:
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            insert_record(conn, page_id="missing")


def test_page_number_unique_within_a_file(db):
    with db.connect() as conn:
        insert_page(conn, "p1")
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert_page(conn, "p2")


def test_deleting_first_page_deletes_the_whole_form(db):
    with db.connect() as conn:
        insert_page(conn, "p1")
        insert_page(conn, "p2", page_number=2, first_page_id="p1")
        insert_record(conn)
        for page_id in ("p1", "p2"):
            conn.execute(
                "INSERT INTO page_image (page_id, mime, sha256, bytes)"
                " VALUES (%s, 'image/jpeg', 'x', '\\x00')",
                (page_id,),
            )
        conn.execute(
            "INSERT INTO record_event (record_id, at, user_id, action)"
            " VALUES ('r1', %s, 'u1', 'created')",
            (NOW,),
        )

        conn.execute("DELETE FROM page WHERE id = 'p1'")

        for table in ("page", "page_image", "record", "record_event"):
            assert count(conn, table) == 0


def test_deleting_user_deletes_their_sessions(db):
    with db.connect() as conn:
        insert_user(conn)
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at, last_seen_at)"
            " VALUES ('h', 'u1', %s, %s, %s)",
            (NOW, NOW, NOW),
        )

        conn.execute("DELETE FROM users WHERE id = 'u1'")

        assert count(conn, "sessions") == 0
