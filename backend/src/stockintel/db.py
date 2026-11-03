"""Database engine and table definitions."""

from functools import lru_cache

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Engine,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    func,
    text,
)

from stockintel.config import get_settings

metadata = MetaData()

# Source trust ranking from the build brief. Lower is more trusted.
# 1 official, 2 licensed API, 3 established news, 4 convenience source.
data_sources = Table(
    "data_sources",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(100), nullable=False, unique=True),
    Column("trust_rank", Integer, nullable=False),
    Column("base_url", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("trust_rank BETWEEN 1 AND 4", name="ck_data_sources_trust_rank"),
)

worker_heartbeats = Table(
    "worker_heartbeats",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("hostname", String(255), nullable=False),
    Column("beat_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def ping(engine: Engine) -> None:
    """Raise if the database cannot answer a query."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
