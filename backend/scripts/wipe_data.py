"""Delete every page, page image and record, with their events and the export log.

    python -m scripts.wipe_data           # asks you to type "delete"
    python -m scripts.wipe_data --yes     # no question

The one command the privacy section promises (SPEC 11, D12). Users stay, so the
team and the judges can still sign in. Uses DATABASE_URL (backend/.env); for the
live database, its External URL with ?sslmode=require.

Owner: B
"""

import argparse
import sys
from collections.abc import Callable

import psycopg

from app.settings import get_settings

CONFIRM = "delete"


def main(
    argv: list[str] | None = None,
    *,
    ask: Callable[[str], str] = input,
    database_url: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.wipe_data")
    parser.add_argument("--yes", action="store_true", help="Don't ask before deleting")
    args = parser.parse_args(argv)

    url = database_url or get_settings().database_url.get_secret_value()
    if not url:
        print("DATABASE_URL is not set (backend/.env).", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        host = conn.info.host
        pages, records = conn.execute(
            "SELECT (SELECT count(*) FROM page), (SELECT count(*) FROM record)"
        ).fetchone()
        if not args.yes:
            print(f"{pages} pages and {records} records on {host}.")
            if ask(f'Type "{CONFIRM}" to delete all of them: ').strip() != CONFIRM:
                print("Nothing deleted.")
                return 1
        # CASCADE: page_image, record and record_event all hang off page.
        conn.execute("TRUNCATE page, export_log CASCADE")
    print(f"Deleted {pages} pages and {records} records. Users are kept.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
