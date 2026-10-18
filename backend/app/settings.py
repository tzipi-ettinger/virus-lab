"""Settings: GEMINI_MODEL, limits, flags (dev cache off by default).

Owner: A
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
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

    # "fake" serves tests/fixtures: no key, no quota, no real data. "gemini" comes
    # with the Gemini provider.
    extraction_provider: Literal["fake"] = "fake"

    # Upload limits (SPEC 9.7)
    max_file_mb: int = Field(20, ge=1)
    max_pages_per_request: int = Field(60, ge=1)
    # The whole request, all files together: it is held in memory, never on disk.
    max_request_mb: int = Field(60, ge=1)
    max_files_per_request: int = Field(20, ge=1)
    # Pages read at once, so at most this many model calls at a time.
    max_concurrency: int = Field(4, ge=1)

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1_000_000

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
