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
    worker_stale_after_seconds: int = Field(default=180, gt=0)
    frontend_origin: str = "http://localhost:5173"

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
