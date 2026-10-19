import psycopg
import pytest

from app.storage.db import SCHEMA_VERSION, SchemaVersionMismatch, init_db, open_pool

NOW = "2026-10-18T10:00:00Z"
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
        " VALUES (%s, %s, 'x', 'Test', %s)",
        (user_id, user_id, NOW),
    )


def insert_page(conn, page_id="p1", page_number=1, first_page_id=None):
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


def test_init_creates_tables_and_sets_version(db):
    with db.connect() as conn:
        tables = {
            row["tablename"]
            for row in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        }
        version = conn.execute("SELECT version FROM schema_meta").fetchone()["version"]

    assert tables == TABLES
    assert version == SCHEMA_VERSION


def test_init_twice_keeps_data(db):
    with db.connect() as conn:
        insert_user(conn)

    db.run(init_again(db))

    with db.connect() as conn:
        assert count(conn, "users") == 1
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


def test_ids_keep_leading_zeros(db):
    with db.connect() as conn:
        insert_user(conn)
        insert_page(conn)
        insert_record(conn, national_id="011223344", commitment_number="0606")

        row = conn.execute("SELECT national_id, commitment_number FROM record").fetchone()

    assert row == {"national_id": "011223344", "commitment_number": "0606"}


def test_status_only_pending_or_approved(db):
    with db.connect() as conn:
        insert_user(conn)
        insert_page(conn)
        with pytest.raises(psycopg.errors.CheckViolation):
            insert_record(conn, status="done")


def test_record_needs_existing_page(db):
    with db.connect() as conn:
        insert_user(conn)
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            insert_record(conn, page_id="missing")


def test_page_number_unique_within_a_file(db):
    with db.connect() as conn:
        insert_user(conn)
        insert_page(conn, "p1")
        with pytest.raises(psycopg.errors.UniqueViolation):
            insert_page(conn, "p2")


def test_deleting_first_page_deletes_the_whole_form(db):
    with db.connect() as conn:
        insert_user(conn)
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
