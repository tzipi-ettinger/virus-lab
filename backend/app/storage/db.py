"""Postgres connection pool and schema setup.

One pool per app (open_pool, from the app's lifespan). Each saved form or request
takes its own connection from it. The schema is created on the first start, and the
server refuses to start on a DB from another schema version.

psycopg's async mode can't run on Windows' default event loop (Proactor). Locally,
`uvicorn --reload` uses a selector loop, and the tests pick one explicitly.

Owner: B
"""

from pathlib import Path

from psycopg import AsyncConnection
from psycopg.rows import dict_row, tuple_row
from psycopg_pool import AsyncConnectionPool

SCHEMA_VERSION = 1
_SCHEMA_SQL = Path(__file__).with_name("schema.sql")
# Any constant: two servers starting at once must not both create the schema.
_INIT_LOCK = 0x76_6C_61_62  # "vlab"


class SchemaVersionMismatch(RuntimeError):
    pass


async def init_db(conn: AsyncConnection) -> None:
    """Create the schema on an empty DB; refuse a DB from another schema version."""
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
