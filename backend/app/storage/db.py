"""Postgres connection pool and schema setup.

One pool per app (open_pool, from the app's lifespan). Each saved form or request
takes its own connection from it. The schema is created on the first start, a DB
from an older version is upgraded (MIGRATIONS), and the server refuses to start on
any other version.

psycopg's async mode can't run on Windows' default event loop (Proactor). Locally,
`uvicorn --reload` uses a selector loop, and the tests pick one explicitly.

Owner: B
"""

from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import AsyncConnectionPool

SCHEMA_VERSION = 2
_SCHEMA_SQL = Path(__file__).with_name("schema.sql")
# Any constant: two servers starting at once must not both create the schema.
_INIT_LOCK = 0x76_6C_61_62  # "vlab"


# version -> the SQL that takes a DB from it to the next version, keeping the data.
MIGRATIONS = {
    # 1 -> 2: the site has no sign-in (21.10), so users, sessions and every
    # "who" column go. Records, pages and images stay as they are.
    1: """
        ALTER TABLE record_event DROP COLUMN user_id;
        ALTER TABLE export_log DROP COLUMN user_id;
        ALTER TABLE record DROP COLUMN created_by, DROP COLUMN approved_by;
        ALTER TABLE page DROP COLUMN created_by;
        DROP TABLE sessions;
        DROP TABLE users;
    """,
}


class SchemaVersionMismatch(RuntimeError):
    pass


async def init_db(conn: AsyncConnection) -> None:
    """Create the schema on an empty DB, upgrade an older one in place, and refuse
    any other version."""
    async with conn.transaction(), conn.cursor(row_factory=tuple_row) as cur:
        await cur.execute("SELECT pg_advisory_xact_lock(%s)", (_INIT_LOCK,))
        await cur.execute("SELECT to_regclass('schema_meta') IS NOT NULL")
        (exists,) = await cur.fetchone()
        if not exists:
            # No parameters, so psycopg sends it as one script of many statements.
            await cur.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
            await cur.execute("INSERT INTO schema_meta (version) VALUES (%s)", (SCHEMA_VERSION,))
            return
        await cur.execute("SELECT version FROM schema_meta")
        row = await cur.fetchone()
        version = row[0] if row else None
        # In the same transaction: a migration that fails leaves the old version whole.
        while version in MIGRATIONS:
            await cur.execute(MIGRATIONS[version])
            version += 1
            await cur.execute("UPDATE schema_meta SET version = %s", (version,))
    if version != SCHEMA_VERSION:
        raise SchemaVersionMismatch(
            f"The database has schema version {version}, the code expects {SCHEMA_VERSION}. "
            "On a local database, run `docker compose down -v` and start again "
            "(it deletes the local data). Never do that on the live database."
        )


async def open_pool(database_url: str, *, max_size: int = 5) -> AsyncConnectionPool:
    """Open the pool and check the schema. Raises if the DB is unreachable or mismatched."""
    pool = AsyncConnectionPool(
        database_url,
        min_size=1,
        max_size=max_size,
        kwargs={"row_factory": dict_row},
        open=False,
    )
    await pool.open(wait=True, timeout=10)
    try:
        async with pool.connection() as conn:
            await init_db(conn)
    except BaseException:
        await pool.close()
        raise
    return pool
