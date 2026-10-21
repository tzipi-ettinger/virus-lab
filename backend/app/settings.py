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

    # SecretStr keeps the keys out of repr, logs and tracebacks. Call
    # .get_secret_value() only where the Gemini clients are built.
    # GEMINI_API_KEYS: comma-separated, one key per Google project. The free-tier
    # quota is per project, so the provider moves to the next key when one runs out.
    gemini_api_keys: SecretStr = SecretStr("")
    # The old single key, still read so an existing .env keeps working.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    frontend_origin: str = "http://localhost:5173"
    # production on the live server (render.yaml): HSTS, and no /docs (app/security.py).
    env: Literal["development", "production"] = "development"
    # Postgres (Dev-B plan B0.3): docker compose locally, Render's internal URL on the
    # live server. SecretStr, since the URL holds the password.
    database_url: SecretStr = SecretStr("")
    # One password for the whole site (app/site_password.py, D22). Empty: the site
    # is open, as in development and tests. The live server sets it in Render.
    site_username: str = "lab"
    site_password: SecretStr = SecretStr("")
    # The built frontend (frontend/dist), served by FastAPI on the live server. Set
    # only in the Docker image; in development Vite serves the page (app/spa.py).
    static_dir: str = ""
    # Keep-alive (app/keep_alive.py): the server pings its own public address so the
    # free Render instance doesn't fall asleep. KEEP_ALIVE_URL wins; on Render,
    # RENDER_EXTERNAL_URL (set by Render itself) is used. Neither: off, as locally.
    keep_alive_url: str = ""
    render_external_url: str = ""
    keep_alive_interval_s: int = Field(600, ge=60)

    # "fake" serves tests/fixtures: no key, no quota, no real data. "gemini" sends
    # each page to GEMINI_MODEL and needs GEMINI_API_KEYS (checked at startup).
    extraction_provider: Literal["fake", "gemini"] = "fake"
    # One model call, retries not included (SPEC 9.7). 180, not 60: on the live
    # server Gemini sometimes took over a minute for one page (21.10).
    provider_timeout_s: int = Field(180, ge=1)
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
                    ("GEMINI_API_KEYS", bool(self.gemini_keys())),
                    ("GEMINI_MODEL", bool(self.gemini_model.strip())),
                )
                if not value
            ]
            if missing:
                raise ValueError(f"EXTRACTION_PROVIDER=gemini needs {' and '.join(missing)}")
        return self

    def gemini_keys(self) -> tuple[SecretStr, ...]:
        """Every key in order, blanks and repeats left out: GEMINI_API_KEYS, then GEMINI_API_KEY."""
        raw = f"{self.gemini_api_keys.get_secret_value()},{self.gemini_api_key.get_secret_value()}"
        keys = dict.fromkeys(key.strip() for key in raw.split(",") if key.strip())
        return tuple(SecretStr(key) for key in keys)

    @property
    def production(self) -> bool:
        return self.env == "production"

    @property
    def keep_alive_base_url(self) -> str:
        return self.keep_alive_url or self.render_external_url

    @property
    def max_file_bytes(self) -> int:
        return self.max_file_mb * 1_000_000

    @property
    def max_request_bytes(self) -> int:
        return self.max_request_mb * 1_000_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
