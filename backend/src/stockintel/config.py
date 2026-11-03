"""Configuration, read only from the environment or the repository's .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    # Required on purpose: there is no default database to fall back to.
    database_url: str = Field(min_length=1)
    worker_heartbeat_seconds: int = Field(default=60, gt=0)
    worker_stale_after_seconds: int = Field(default=259200, gt=0)
    frontend_origin: str = "http://localhost:5173"

    # Data sources. Empty means the feed reports an error when run, never a fallback.
    tiingo_api_token: str = ""
    fred_api_key: str = ""
    sec_contact_email: str = ""
    universe_size: int = Field(default=480, gt=0)
    price_history_start: str = "2010-01-01"

    # Production refuses to start without a password.
    app_env: str = "development"
    dashboard_password: str = ""
    static_dir: str = ""

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        """Hosts such as Neon give a plain postgresql:// address. Select the installed driver."""
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value.removeprefix(prefix)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
