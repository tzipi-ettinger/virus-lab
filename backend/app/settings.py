"""Settings: GEMINI_MODEL, limits, flags (dev cache off by default).

Owner: A
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SecretStr keeps the key out of repr, logs and tracebacks. Call
    # .get_secret_value() only where the Gemini client is built.
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
