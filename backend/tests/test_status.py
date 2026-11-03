from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError

from stockintel import main
from stockintel.db import data_sources, worker_heartbeats
from stockintel.status import get_status
from stockintel.worker import record_heartbeat


def test_status_healthy_after_real_heartbeat(engine):
    record_heartbeat(engine)
    result = get_status(engine, stale_after_seconds=180)
    assert result["healthy"] is True
    assert result["migrations"]["current"] == result["migrations"]["expected"] == "0001"
    assert result["worker"]["state"] == "ok"


def test_worker_that_never_ran_is_unhealthy(engine):
    result = get_status(engine, stale_after_seconds=180)
    assert result["healthy"] is False
    assert result["worker"]["state"] == "never_run"


def test_old_heartbeat_is_flagged_stale(engine):
    with engine.begin() as conn:
        conn.execute(
            insert(worker_heartbeats).values(
                hostname="test", beat_at=datetime.now(UTC) - timedelta(hours=1)
            )
        )
    result = get_status(engine, stale_after_seconds=180)
    assert result["healthy"] is False
    assert result["worker"]["state"] == "stale"


def test_unreachable_database_reports_error_without_secrets():
    secret = "do-not-leak"
    bad = create_engine(f"postgresql+psycopg://nobody:{secret}@127.0.0.1:1/none")
    result = get_status(bad, stale_after_seconds=180)
    assert result["healthy"] is False
    assert result["database"]["state"] == "error"
    assert result["worker"]["state"] == "not_verified"
    assert secret not in str(result)


def test_status_endpoint_returns_503_when_database_down(monkeypatch, database_url):
    bad = create_engine("postgresql+psycopg://nobody:x@127.0.0.1:1/none")
    monkeypatch.setattr(main, "get_engine", lambda: bad)
    response = TestClient(main.app).get("/api/status")
    assert response.status_code == 503
    assert response.json()["database"]["state"] == "error"


def test_status_endpoint_returns_200_when_healthy(monkeypatch, engine):
    record_heartbeat(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    response = TestClient(main.app).get("/api/status")
    assert response.status_code == 200
    assert response.json()["healthy"] is True


def test_trust_rank_outside_brief_is_rejected(engine):
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            insert(data_sources).values(name="bad", trust_rank=5, base_url="https://example.test")
        )
