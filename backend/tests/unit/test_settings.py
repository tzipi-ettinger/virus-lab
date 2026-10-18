from pathlib import Path

from app.settings import ENV_FILE, Settings


def test_api_key_is_masked(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-key-123")
    settings = Settings(_env_file=None)

    assert "real-key-123" not in repr(settings)
    assert "real-key-123" not in settings.model_dump_json()
    assert settings.gemini_api_key.get_secret_value() == "real-key-123"


def test_env_file_is_found_from_any_working_directory():
    backend = Path(__file__).resolve().parents[2]

    assert ENV_FILE == backend / ".env"
    assert Settings.model_config["env_file"] == ENV_FILE
