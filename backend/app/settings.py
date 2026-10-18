"""Settings: GEMINI_MODEL, limits, flags (dev cache off by default).

Owner: A
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
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

    # Upload limits (SPEC 9.5)
    max_file_mb: int = 20
    max_pages_per_request: int = 60

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
