"""Settings: GEMINI_MODEL, limits, flags (dev cache off by default).

Owner: A
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, wherever the server is started from: a relative path is read from
# the working directory, so starting uvicorn from the repo root would silently
# run without the key.
ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # SecretStr keeps the key out of repr, logs and tracebacks. Call
    # .get_secret_value() only where the Gemini client is built.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    frontend_origin: str = "http://localhost:5173"
    # Postgres (Dev-B plan B0.3): docker compose locally, Render's internal URL on the
    # live server. SecretStr, since the URL holds the password.
    database_url: SecretStr = SecretStr("")

    # "fake" serves tests/fixtures: no key, no quota, no real data. "gemini" sends
    # each page to GEMINI_MODEL and needs GEMINI_API_KEY (checked at startup).
    extraction_provider: Literal["fake", "gemini"] = "fake"
    # One model call, retries not included (SPEC 9.7).
    provider_timeout_s: int = Field(60, ge=1)
    # Dev only, sample files only: answer a page Gemini already read from
    # backend/.cache/ (gitignored) instead of a new call. Never on the live server.
    extraction_cache: bool = False

    # Upload limits (SPEC 9.7)
    max_file_mb: int = Field(20, ge=1)
    max_pages_per_request: int = Field(60, ge=1)
    # The whole request, all files together: it is held in memory, never on disk.
    max_request_mb: int = Field(60, ge=1)
    max_files_per_request: int = Field(20, ge=1)
    # Pages read at once within one upload. The Gemini provider holds the same limit
    # for the whole server, so two uploads at once still make at most this many calls.
    max_concurrency: int = Field(4, ge=1)

    @model_validator(mode="after")
    def _gemini_needs_key_and_model(self) -> "Settings":
        # Refuse to start rather than fail on every page. The message never shows the key.
        if self.extraction_provider == "gemini":
            missing = [
                name
                for name, value in (
                    ("GEMINI_API_KEY", self.gemini_api_key.get_secret_value()),
                    ("GEMINI_MODEL", self.gemini_model),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(f"EXTRACTION_PROVIDER=gemini needs {' and '.join(missing)}")
        return self

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1_000_000

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
