"""SQLite connection and schema setup.

One connection per request (connect), schema created once on startup (init_db).
The DB path comes from the caller; wiring to settings/main.py waits for
Developer A's approval (docs/GUIDELINES-V2-CHANGES.md, A8).

Owner: B
"""

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1
_SCHEMA_SQL = Path(__file__).with_name("schema.sql")


class SchemaVersionMismatch(RuntimeError):
    pass


def connect(path: str | Path) -> sqlite3.Connection:
    # check_same_thread=False: FastAPI may run a request's dependency and
    # handler on different threads. The connection is never shared across requests.
    conn = sqlite3.connect(path, timeout=5, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(path: str | Path) -> None:
    """Create the schema on a new DB; refuse to start on a DB from another schema version."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(_SCHEMA_SQL.read_text(encoding="utf-8"))
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        elif version != SCHEMA_VERSION:
            raise SchemaVersionMismatch(
                f"{path} has schema version {version}, code expects {SCHEMA_VERSION}. "
                f"Delete {path} and restart (it is local dev data)."
            )
    finally:
        conn.close()
