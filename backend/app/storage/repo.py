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


# --- Reading records

# A record with what the contract shows next to it: its form's pages and who
# approved or last edited it (by username, from users and record_event).
_RECORD_SELECT = """
SELECT r.*,
       p.source_filename,
       p.page_number,
       COALESCE(cont.numbers, '{}') AS continuation_pages,
       COALESCE(cont.ids, '{}') AS continuation_page_ids,
       approver.username AS approved_by_username,
       (SELECT u.username FROM record_event e JOIN users u ON u.id = e.user_id
         WHERE e.record_id = r.id AND e.action IN ('corrected', 'confirmed')
         ORDER BY e.at DESC, e.id DESC LIMIT 1) AS updated_by_username
  FROM record r
  JOIN page p ON p.id = r.page_id
  LEFT JOIN users approver ON approver.id = r.approved_by
  LEFT JOIN LATERAL (
       SELECT array_agg(c.page_number ORDER BY c.page_number) AS numbers,
              array_agg(c.id ORDER BY c.page_number) AS ids
         FROM page c WHERE c.first_page_id = r.page_id) cont ON TRUE
"""


async def get_record(conn: AsyncConnection, record_id: str, *, lock: bool = False) -> dict | None:
    """One record row; `lock` holds it until the transaction ends (patch, approve, delete)."""
    lock_sql = " FOR UPDATE OF r" if lock else ""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(f"{_RECORD_SELECT} WHERE r.id = %s{lock_sql}", (record_id,))
        return await cur.fetchone()


async def get_siblings(conn: AsyncConnection, record: dict, *, lock: bool = False) -> list[dict]:
    """The other records of the same form (same first page), in commitment order."""
    lock_sql = " FOR UPDATE OF r" if lock else ""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            f"{_RECORD_SELECT} WHERE r.page_id = %s AND r.id <> %s"
            f" ORDER BY r.commitment_idx{lock_sql}",
            (record["page_id"], record["id"]),
        )
        return await cur.fetchall()


def _like(text: str) -> str:
    """A LIKE pattern that matches `text` anywhere, with % and _ taken literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


# The filters' SQL. The keys are fixed here, never taken from the request.
_FILTER_SQL = {
    "search": "r.search_text LIKE %s",
    "status": "r.status = %s",
    "needs_review": "r.needs_review = %s",
    "sender": "r.sender = %s",
    "form_type": "r.form_type = %s",
    "date_from": "r.received_date >= %s",
    "date_to": "r.received_date <= %s",
}


def _where(conditions: dict[str, object]) -> tuple[str, list[object]]:
    """AND of the filters that are set."""
    parts, params = [], []
    for key, value in conditions.items():
        if value is None:
            continue
        parts.append(_FILTER_SQL[key])
        params.append(_like(value) if key == "search" else value)
    return (" WHERE " + " AND ".join(parts)) if parts else "", params


async def list_records(
    conn: AsyncConnection,
    *,
    search: str | None,
    status: str | None,
    needs_review: bool | None,
    sender: str | None,
    form_type: str | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int, dict]:
    """A page of rows, the total before paging, and the screen's counters.

    `search` is already folded like search_text. The counters skip the status and
    needs_review filters, so they stay put while the user switches between them.
    """
    others = {
        "search": search,
        "sender": sender,
        "form_type": form_type,
        "date_from": date_from,
        "date_to": date_to,
    }
    where, params = _where({**others, "status": status, "needs_review": needs_review})
    count_where, count_params = _where(others)
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT r.id, r.page_id, r.commitment_idx, r.status, r.needs_review,"
            " r.first_name, r.last_name, r.national_id, r.commitment_number,"
            " r.central_values, r.sender, r.form_type, r.received_date,"
            " r.created_at, r.approved_at, p.source_filename, p.page_number"
            f" FROM record r JOIN page p ON p.id = r.page_id{where}"
            " ORDER BY r.created_at DESC, p.page_number, r.commitment_idx, r.id"
            " LIMIT %s OFFSET %s",
            (*params, limit, offset),
        )
        rows = await cur.fetchall()
        await cur.execute(f"SELECT count(*) AS n FROM record r{where}", params)
        total = (await cur.fetchone())["n"]
        await cur.execute(
            "SELECT count(*) FILTER (WHERE r.status = 'pending') AS pending,"
            " count(*) FILTER (WHERE r.status = 'approved') AS approved,"
            " count(*) FILTER (WHERE r.status = 'pending' AND r.needs_review) AS needs_review"
            f" FROM record r{count_where}",
            count_params,
        )
        counts = await cur.fetchone()
    return rows, total, counts


async def commitment_taken(conn: AsyncConnection, number: str, *, except_id: str) -> bool:
    """Whether another record already has this commitment number (A4)."""
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "SELECT EXISTS (SELECT 1 FROM record WHERE commitment_number = %s AND id <> %s)"
            " AS taken",
            (number, except_id),
        )
        return (await cur.fetchone())["taken"]


# --- Changing records. The caller holds the row lock and has checked version and status.


async def update_record(
    conn: AsyncConnection,
    *,
    record_id: str,
    needs_review: bool,
    fields: dict,
    central_numbers: list[dict],
    national_id: str | None,
    commitment_number: str | None,
    central_values: list[str],
    first_name: str | None,
    last_name: str | None,
    sender: str | None,
    received_date: date | None,
    search_text: str,
    now: datetime,
) -> None:
    """Save edited fields with their effective columns, and bump the version."""
    await conn.execute(
        "UPDATE record SET needs_review = %s, fields = %s, central_numbers = %s,"
        " national_id = %s, commitment_number = %s, central_values = %s, first_name = %s,"
        " last_name = %s, sender = %s, received_date = %s, search_text = %s,"
        " version = version + 1, updated_at = %s WHERE id = %s",
        (
            needs_review,
            Jsonb(fields),
            Jsonb(central_numbers),
            national_id,
            commitment_number,
            central_values,
            first_name,
            last_name,
            sender,
            received_date,
            search_text,
            now,
            record_id,
        ),
    )


async def approve_record(
    conn: AsyncConnection, record_id: str, *, user_id: str, now: datetime
) -> None:
    await conn.execute(
        "UPDATE record SET status = 'approved', approved_at = %s, approved_by = %s,"
        " version = version + 1, updated_at = %s WHERE id = %s",
        (now, user_id, now, record_id),
    )


async def delete_record(conn: AsyncConnection, record_id: str, page_id: str) -> None:
    """Delete one record. When it was its form's last, the pages and images go too,
    so nothing of a patient's form stays without a record that needs it (D4)."""
    await conn.execute("DELETE FROM record WHERE id = %s", (record_id,))
    await conn.execute(
        "DELETE FROM page WHERE id = %s AND NOT EXISTS (SELECT 1 FROM record WHERE page_id = %s)",
        (page_id, page_id),
    )
