from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import ENV_FILE, Settings


@pytest.fixture(autouse=True)
def no_keys_from_the_shell(monkeypatch):
    # _env_file=None skips .env, not the environment: a key exported in the shell
    # would turn "no key" tests green-to-red on that machine only.
    monkeypatch.delenv("GEMINI_API_KEYS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def test_api_key_is_masked(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-key-123")
    settings = Settings(_env_file=None)

    assert "real-key-123" not in repr(settings)
    assert "real-key-123" not in settings.model_dump_json()
    assert settings.gemini_api_key.get_secret_value() == "real-key-123"


def test_database_url_is_masked(monkeypatch):
    url = "postgresql://user:db-pass-123@db.example:5432/app"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(_env_file=None)

    assert "db-pass-123" not in repr(settings)
    assert "db-pass-123" not in settings.model_dump_json()
    assert settings.database_url.get_secret_value() == url


def test_env_file_is_found_from_any_working_directory():
    backend = Path(__file__).resolve().parents[2]

    assert ENV_FILE == backend / ".env"
    assert Settings.model_config["env_file"] == ENV_FILE


def test_gemini_needs_a_key_and_a_model():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, extraction_provider="gemini")

    assert "GEMINI_API_KEYS and GEMINI_MODEL" in str(error.value)


def test_keys_are_read_from_a_comma_separated_list(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key-1, key-2,,key-3 ,")
    settings = Settings(_env_file=None)

    assert keys(settings) == ["key-1", "key-2", "key-3"]
    assert "key-2" not in repr(settings)
    assert "key-2" not in repr(settings.gemini_keys())


def test_the_old_single_key_still_works_and_comes_last(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key-1,key-2")
    monkeypatch.setenv("GEMINI_API_KEY", "old-key")

    assert keys(Settings(_env_file=None)) == ["key-1", "key-2", "old-key"]


def test_a_key_listed_twice_is_used_once(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEYS", "key-1,key-1")
    monkeypatch.setenv("GEMINI_API_KEY", "key-1")

    assert keys(Settings(_env_file=None)) == ["key-1"]


def keys(settings: Settings) -> list[str]:
    return [key.get_secret_value() for key in settings.gemini_keys()]


def test_only_commas_counts_as_no_key():
    with pytest.raises(ValidationError) as error:
        Settings(
            _env_file=None, extraction_provider="gemini", gemini_api_keys=" , ,", gemini_model="m"
        )

    assert "GEMINI_API_KEYS" in str(error.value)


def test_gemini_with_a_key_and_a_model_loads_without_showing_the_key():
    settings = Settings(
        _env_file=None,
        extraction_provider="gemini",
        gemini_api_key="real-key-123",
        gemini_model="gemini-test",
    )

    assert settings.extraction_provider == "gemini"
    assert "real-key-123" not in repr(settings)


def test_a_blank_key_counts_as_missing():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, extraction_provider="gemini", gemini_api_key=" ", gemini_model="m")

    assert "GEMINI_API_KEY" in str(error.value)
