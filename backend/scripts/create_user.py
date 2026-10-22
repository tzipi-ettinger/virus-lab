"""Create a user: the only way to get one, since there is no sign-up (Dev-B plan 2.6).

    python -m scripts.create_user <username> [--name "Display name"]

The password is asked twice at a prompt, so it never lands in the shell history.
Uses DATABASE_URL (backend/.env); for the live database, its External URL with
?sslmode=require.

Owner: B
"""

import argparse
import getpass
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

import psycopg

from app.auth.passwords import MIN_LENGTH, hash_password
from app.settings import get_settings


def main(
    argv: list[str] | None = None,
    *,
    ask: Callable[[str], str] = getpass.getpass,
    database_url: str | None = None,
) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.create_user")
    parser.add_argument("username")
    parser.add_argument("--name", help="Display name (default: the username)")
    args = parser.parse_args(argv)

    password = ask("Password: ")
    if len(password) < MIN_LENGTH:
        print(f"The password needs at least {MIN_LENGTH} characters.", file=sys.stderr)
        return 1
    if ask("Password again: ") != password:
        print("The passwords don't match.", file=sys.stderr)
        return 1

    url = database_url or get_settings().database_url.get_secret_value()
    if not url:
        print("DATABASE_URL is not set (backend/.env).", file=sys.stderr)
        return 1
    with psycopg.connect(url, autocommit=True) as conn:
        try:
            conn.execute(
                "INSERT INTO users (id, username, password_hash, display_name, created_at)"
                " VALUES (%s, %s, %s, %s, %s)",
                (
                    str(uuid4()),
                    args.username,
                    hash_password(password),
                    args.name or args.username,
                    datetime.now(UTC),
                ),
            )
        except psycopg.errors.UniqueViolation:
            print(f"User {args.username} already exists.", file=sys.stderr)
            return 1
    print(f"Created user {args.username}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
