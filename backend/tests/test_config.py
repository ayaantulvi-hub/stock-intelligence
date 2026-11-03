import pytest
from pydantic import ValidationError

from stockintel.config import Settings


def test_database_url_has_no_default(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_plain_postgres_address_uses_installed_driver():
    settings = Settings(_env_file=None, database_url="postgresql://u:p@host/db?sslmode=require")
    assert settings.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
