"""Tests run against a real PostgreSQL database named by TEST_DATABASE_URL."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

BACKEND = Path(__file__).resolve().parents[1]

# Set before any stockintel import, because settings are cached on first read.
# Without this, tests could migrate the development database named in .env.
TEST_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_URL:
    os.environ["DATABASE_URL"] = TEST_URL


@pytest.fixture(scope="session")
def database_url():
    if not TEST_URL:
        pytest.fail("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    assert "test" in TEST_URL.rsplit("/", 1)[-1], "refusing to use a non-test database"
    return TEST_URL


@pytest.fixture(scope="session")
def migrated(database_url):
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(config, "head")
    return config


@pytest.fixture
def engine(migrated, database_url):
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """TRUNCATE worker_heartbeats, feed_runs, validation_issues, securities,
                   fetches, price_bars, filings, economic_observations, backtest_runs,
                   backtest_results, model_evaluations, forecasts,
                   forecast_scores, company_facts, insider_transactions,
                   insider_documents, factor_tests, positions,
                   model_comparisons, historic_float, fed_meetings, alerts,
                   watchlist, practice_trades, journal_entries, stop_studies RESTART IDENTITY CASCADE"""
            )
        )
    yield engine
    engine.dispose()
