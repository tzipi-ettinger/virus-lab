from pathlib import Path

import pytest
from pydantic import ValidationError

from app.settings import ENV_FILE, Settings


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

    assert "GEMINI_API_KEY and GEMINI_MODEL" in str(error.value)


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
