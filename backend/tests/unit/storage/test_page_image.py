"""repo.get_page_image against a real Postgres (Dev-B plan B1.2)."""

from datetime import UTC, datetime

import pytest

from app.storage import repo

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
JPEG = b"\xff\xd8\xff\xe0 not really a jpeg \xff\xd9"


@pytest.fixture
def page(db):
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO users (id, username, password_hash, display_name, created_at)"
            " VALUES ('u1', 'tester', 'x', 'Tester', %s)",
            (NOW,),
        )
        conn.execute(
            "INSERT INTO page (id, file_id, source_filename, page_number, created_at, created_by)"
            " VALUES ('p1', 'f1', 'a.pdf', 1, %s, 'u1')",
            (NOW,),
        )
    return "p1"


def read(db, page_id):
    async def go():
        async with await db.connect_async() as conn:
            return await repo.get_page_image(conn, page_id)

    return db.run(go())


def test_reads_back_the_saved_bytes(db, page):
    async def save():
        async with await db.connect_async() as conn:
            await repo.insert_page_image(conn, page, JPEG)
            await conn.commit()

    db.run(save())

    assert read(db, page) == JPEG


def test_a_page_without_an_image_or_an_unknown_page_is_none(db, page):
    assert read(db, page) is None
    assert read(db, "nope") is None
