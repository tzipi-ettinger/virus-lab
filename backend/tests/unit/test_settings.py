from app.settings import Settings


def test_api_key_is_masked(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "real-key-123")
    settings = Settings(_env_file=None)

    assert "real-key-123" not in repr(settings)
    assert "real-key-123" not in settings.model_dump_json()
    assert settings.gemini_api_key.get_secret_value() == "real-key-123"
