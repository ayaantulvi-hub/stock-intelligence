"""Reports real system state. Anything that cannot be confirmed is reported as such."""

from datetime import UTC, datetime
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import SQLAlchemyError

from stockintel.db import ping, worker_heartbeats

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def expected_revision() -> str | None:
    config = Config()
    config.set_main_option("script_location", str(MIGRATIONS_DIR))
    return ScriptDirectory.from_config(config).get_current_head()


def get_status(engine: Engine, stale_after_seconds: int) -> dict:
    now = datetime.now(UTC)
    database = {"state": "ok", "detail": None}
    migrations = {"state": "not_verified", "current": None, "expected": expected_revision()}
    worker = {"state": "not_verified", "last_heartbeat": None, "age_seconds": None}

    try:
        ping(engine)
    except SQLAlchemyError as exc:
        # The class name only: driver messages can contain connection details.
        database = {"state": "error", "detail": type(exc).__name__}
        return _result(now, database, migrations, worker)

    try:
        with engine.connect() as conn:
            current = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            migrations["current"] = current
            migrations["state"] = "ok" if current == migrations["expected"] else "error"
            last = conn.execute(
                select(worker_heartbeats.c.beat_at)
                .order_by(worker_heartbeats.c.beat_at.desc())
                .limit(1)
            ).scalar()
    except SQLAlchemyError:
        migrations["state"] = "error"
        return _result(now, database, migrations, worker)

    if last is None:
        worker["state"] = "never_run"
    else:
        age = (now - last).total_seconds()
        worker = {
            "state": "ok" if age <= stale_after_seconds else "stale",
            "last_heartbeat": last.isoformat(),
            "age_seconds": round(age),
        }
    return _result(now, database, migrations, worker)


def _result(now: datetime, database: dict, migrations: dict, worker: dict) -> dict:
    healthy = (
        database["state"] == "ok" and migrations["state"] == "ok" and worker["state"] == "ok"
    )
    return {
        "healthy": healthy,
        "checked_at": now.isoformat(),
        "database": database,
        "migrations": migrations,
        "worker": worker,
    }
