"""Shared fixtures: a real Postgres for storage, auth and API tests (Dev-B plan 7.3).

`docker compose up -d db` (repo root) creates the test database. CI points
TEST_DATABASE_URL at its own Postgres service.
"""

import asyncio
import os
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

import psycopg
import pytest
from psycopg.rows import dict_row

from app.storage.db import init_db

# 127.0.0.1, not localhost: on Windows, localhost tries IPv6 first, and docker
# compose publishes the port on IPv4 only, so every connection would wait for a timeout.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://virus_lab:virus_lab@127.0.0.1:5432/virus_lab_test?connect_timeout=5",
)


def run[T](coro: Coroutine[Any, Any, T]) -> T:
    # psycopg's async mode can't use Windows' default (Proactor) event loop.
    return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)


@dataclass(frozen=True)
class Database:
    url: str

    def connect(self) -> psycopg.Connection:
        """A plain connection for arranging and checking rows. Each statement commits."""
        return psycopg.connect(self.url, autocommit=True, row_factory=dict_row)

    async def connect_async(self) -> psycopg.AsyncConnection:
        """What the app gets from its pool."""
        return await psycopg.AsyncConnection.connect(self.url, row_factory=dict_row)

    def run[T](self, coro: Coroutine[Any, Any, T]) -> T:
        return run(coro)


async def _init(url: str) -> None:
    async with await psycopg.AsyncConnection.connect(url) as conn:
        await init_db(conn)


@pytest.fixture(scope="session")
def _test_database() -> Database:
    """Wipe the test database and create the schema, once per run."""
    try:
        conn = psycopg.connect(TEST_DATABASE_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError as exc:
        pytest.fail(
            f"No test database ({type(exc).__name__}). From the repo root, run "
            "`docker compose up -d db`, or set TEST_DATABASE_URL.",
            pytrace=False,
        )
    with conn:
        name = conn.execute("SELECT current_database()").fetchone()[0]
        if not name.endswith("_test"):  # this fixture deletes everything in it
            pytest.fail(f"TEST_DATABASE_URL must name a *_test database, not {name}")
        conn.execute("DROP SCHEMA public CASCADE")
        conn.execute("CREATE SCHEMA public")
    run(_init(TEST_DATABASE_URL))
    return Database(TEST_DATABASE_URL)


@pytest.fixture
def db(_test_database: Database) -> Database:
    """The test database, with every table emptied (the schema stays)."""
    with _test_database.connect() as conn:
        tables = [
            row["tablename"]
            for row in conn.execute(
                "SELECT tablename FROM pg_tables"
                " WHERE schemaname = 'public' AND tablename <> 'schema_meta'"
            )
        ]
        conn.execute(f"TRUNCATE {', '.join(tables)} RESTART IDENTITY CASCADE")
    return _test_database
