from app.auth.passwords import verify_password
from scripts.create_user import main

PASSWORD = "correct horse battery"


def answers(*values):
    replies = iter(values)
    return lambda _prompt: next(replies)


def users(db):
    with db.connect() as conn:
        return conn.execute("SELECT username, display_name, password_hash FROM users").fetchall()


def test_creates_a_user_with_a_hashed_password(db, capsys):
    code = main(["dana", "--name", "דנה"], ask=answers(PASSWORD, PASSWORD), database_url=db.url)

    assert code == 0
    [user] = users(db)
    assert (user["username"], user["display_name"]) == ("dana", "דנה")
    assert verify_password(PASSWORD, user["password_hash"])
    assert PASSWORD not in capsys.readouterr().out


def test_display_name_defaults_to_the_username(db):
    main(["dana"], ask=answers(PASSWORD, PASSWORD), database_url=db.url)

    assert users(db)[0]["display_name"] == "dana"


def test_short_password_is_refused(db, capsys):
    code = main(["dana"], ask=answers("short pass"), database_url=db.url)

    assert code == 1
    assert "12" in capsys.readouterr().err
    assert users(db) == []


def test_passwords_that_differ_are_refused(db):
    code = main(["dana"], ask=answers(PASSWORD, PASSWORD + "!"), database_url=db.url)

    assert code == 1
    assert users(db) == []


def test_existing_username_is_refused(db, capsys):
    main(["dana"], ask=answers(PASSWORD, PASSWORD), database_url=db.url)

    code = main(["dana"], ask=answers(PASSWORD, PASSWORD), database_url=db.url)

    assert code == 1
    assert "already exists" in capsys.readouterr().err
    assert len(users(db)) == 1
