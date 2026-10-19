"""All SQL for records: one function per statement, no logic.

The logic (what to save, duplicates, events) is in storage/service.py. Every
function runs on the caller's connection, inside the caller's transaction.

Owner: B
"""

import hashlib
from datetime import date, datetime

from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb


async def lock_commitments(conn: AsyncConnection, numbers: list[str]) -> None:
    """Hold each commitment number until the transaction ends.

    Sorted, so two saves that share numbers always lock them in the same order and
    can't deadlock. The second one waits, then sees the first one's records.
    """
    for number in sorted(set(numbers)):
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"commitment:{number}",)
        )


async def existing_commitments(conn: AsyncConnection, numbers: list[str]) -> set[str]:
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT DISTINCT commitment_number FROM record WHERE commitment_number = ANY(%s)",
            (list(numbers),),
        )
        return {row["commitment_number"] for row in await cur.fetchall()}


async def insert_page(
    conn: AsyncConnection,
    *,
    page_id: str,
    file_id: str,
    source_filename: str,
    page_number: int,
    rotation: int,
    first_page_id: str | None,
    now: datetime,
    user_id: str,
) -> None:
    await conn.execute(
        "INSERT INTO page (id, file_id, source_filename, page_number, rotation,"
        " first_page_id, created_at, created_by) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (page_id, file_id, source_filename, page_number, rotation, first_page_id, now, user_id),
    )


async def insert_page_image(conn: AsyncConnection, page_id: str, jpeg: bytes) -> None:
    await conn.execute(
        "INSERT INTO page_image (page_id, mime, sha256, bytes) VALUES (%s, 'image/jpeg', %s, %s)",
        (page_id, hashlib.sha256(jpeg).hexdigest(), jpeg),
    )


async def get_page_image(conn: AsyncConnection, page_id: str) -> bytes | None:
    """The saved JPEG of one page, or None when there is no such page."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute("SELECT bytes FROM page_image WHERE page_id = %s", (page_id,))
        row = await cur.fetchone()
    return bytes(row["bytes"]) if row else None


async def insert_record(
    conn: AsyncConnection,
    *,
    record_id: str,
    page_id: str,
    commitment_idx: int,
    needs_review: bool,
    form_type: str,
    fields: dict,
    central_numbers: list[dict],
    issues: list[dict],
    national_id: str | None,
    commitment_number: str | None,
    central_values: list[str],
    first_name: str | None,
    last_name: str | None,
    sender: str | None,
    received_date: date | None,
    search_text: str,
    now: datetime,
    user_id: str,
) -> None:
    await conn.execute(
        "INSERT INTO record (id, page_id, commitment_idx, needs_review, form_type,"
        " fields, central_numbers, issues, national_id, commitment_number, central_values,"
        " first_name, last_name, sender, received_date, search_text,"
        " created_at, created_by, updated_at)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (
            record_id,
            page_id,
            commitment_idx,
            needs_review,
            form_type,
            Jsonb(fields),
            Jsonb(central_numbers),
            Jsonb(issues),
            national_id,
            commitment_number,
            central_values,
            first_name,
            last_name,
            sender,
            received_date,
            search_text,
            now,
            user_id,
            now,
        ),
    )


async def insert_event(
    conn: AsyncConnection,
    *,
    record_id: str,
    action: str,
    user_id: str,
    now: datetime,
    field: str | None = None,
) -> None:
    """Who did what, to which field, and when. Never the values (D13)."""
    await conn.execute(
        "INSERT INTO record_event (record_id, at, user_id, action, field)"
        " VALUES (%s, %s, %s, %s, %s)",
        (record_id, now, user_id, action, field),
    )
