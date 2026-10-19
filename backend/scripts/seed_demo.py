"""Load the challenge's sample forms into a database as pending records, for a demo.

    python -m scripts.seed_demo <file or folder>... --user <username>

The same path as an upload on the site: each file is read with the provider in
backend/.env (EXTRACTION_PROVIDER, and EXTRACTION_CACHE to reuse pages Gemini
already read), then saved through form_saver as that user. One file at a time,
and it stops when the daily quota runs out.

Only the challenge's sample files: never a real patient's form. Uses DATABASE_URL;
for the live database, its External URL with ?sslmode=require. Start again with
`python -m scripts.wipe_data`.

Owner: B
"""

import argparse
import asyncio
import sys
from pathlib import Path

from psycopg.rows import dict_row

from app.api.extract import get_provider
from app.clock import israel_today
from app.extraction.provider import ExtractionProvider
from app.pipeline.service import UploadedFile, extract_files
from app.schemas.api import User
from app.settings import Settings, get_settings
from app.storage.db import open_pool
from app.storage.service import form_saver

SUFFIXES = {".pdf", ".jpg", ".jpeg", ".png"}


def find_files(paths: list[str]) -> list[Path]:
    """The given files, and the forms directly inside the given folders, in name order."""
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found += sorted(p for p in path.iterdir() if p.suffix.lower() in SUFFIXES)
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(raw)
    return found


async def seed(
    files: list[Path],
    username: str,
    *,
    settings: Settings,
    provider: ExtractionProvider,
    database_url: str,
) -> int:
    pool = await open_pool(database_url)
    try:
        async with pool.connection() as conn:
            row = await (
                await conn.cursor(row_factory=dict_row).execute(
                    "SELECT id, username, display_name FROM users"
                    " WHERE username = %s AND is_active",
                    (username,),
                )
            ).fetchone()
        if row is None:
            print(f"No active user {username}. Create one with scripts.create_user.")
            return 1
        user = User(**row)
        total = 0
        for path in files:
            result = await extract_files(
                [UploadedFile(filename=path.name, data=path.read_bytes())],
                provider,
                today=israel_today(),
                max_bytes=settings.max_file_bytes,
                max_pages=settings.max_pages_per_request,
                max_concurrency=settings.max_concurrency,
                save_form=form_saver(pool, user),
            )
            saved = sum(len(form.records) for form in result.forms)
            total += saved
            pages = sum(file.page_count for file in result.files)
            # Counts only: the records themselves are patients' data.
            print(
                f"{path.name}: {pages} pages, {saved} records saved,"
                f" {len(result.failed_pages)} pages failed"
            )
            if result.quota_exhausted:
                print("The daily quota ran out. Run again tomorrow for the files left.")
                break
        print(f"{total} records saved as {username}.")
        return 0
    finally:
        await pool.close()


def main(
    argv: list[str] | None = None,
    *,
    settings: Settings | None = None,
    provider: ExtractionProvider | None = None,
    database_url: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.seed_demo")
    parser.add_argument("paths", nargs="+", help="PDF / JPG / PNG files, or folders of them")
    parser.add_argument("--user", required=True, help="Saved as this user (created_by)")
    args = parser.parse_args(argv)

    settings = settings or get_settings()
    url = database_url or settings.database_url.get_secret_value()
    if not url:
        print("DATABASE_URL is not set (backend/.env).", file=sys.stderr)
        return 1
    try:
        files = find_files(args.paths)
    except FileNotFoundError as exc:
        print(f"Not found: {exc}", file=sys.stderr)
        return 1
    if not files:
        print("No PDF, JPG or PNG files there.", file=sys.stderr)
        return 1
    coro = seed(
        files,
        args.user,
        settings=settings,
        provider=provider or get_provider(settings),
        database_url=url,
    )
    # psycopg's async mode can't use Windows' default (Proactor) event loop.
    return asyncio.run(coro, loop_factory=asyncio.SelectorEventLoop)


if __name__ == "__main__":
    sys.exit(main())
