"""The 100-year market study: reading the French library file, storing it, and the trend rule."""

import io
import zipfile
from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel.ingest import run_market_history
from stockintel.providers.base import FeedError, Provenance
from stockintel.providers.french import MIN_ROWS, parse_daily
from stockintel.quant import studies

NOW = datetime(2026, 11, 23, tzinfo=UTC)


def _zip(lines: list[str]) -> bytes:
    """TEST FIXTURE: a zipped CSV laid out like the library's daily factor file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("F-F_Research_Data_Factors_daily.CSV", "\n".join(lines))
    return buffer.getvalue()


def _rows(count: int, start: date = date(1926, 7, 1)) -> list[str]:
    days = pd.bdate_range(start, periods=count)
    return [f"{d:%Y%m%d},    0.10,   -0.25,   -0.27,    0.009" for d in days]


def _file(count: int = MIN_ROWS) -> bytes:
    header = ["This file was created using the 202609 CRSP database.", "", ",Mkt-RF,SMB,HML,RF"]
    return _zip(header + _rows(count) + ["", "Copyright 2026 Eugene F. Fama and Kenneth R. French"])


def test_reads_percent_as_decimals_and_skips_notes():
    rows = parse_daily(_file())
    assert len(rows) == MIN_ROWS
    assert rows[0] == (date(1926, 7, 1), pytest.approx(0.001), pytest.approx(0.00009))


@pytest.mark.parametrize(
    "content, problem",
    [
        (b"not a zip", "readable zip"),
        (_file(100), "only 100 daily rows"),
        (_zip(["no header here"] + _rows(MIN_ROWS)), "no Mkt-RF column"),
    ],
)
def test_broken_files_raise_instead_of_storing_bad_data(content, problem):
    with pytest.raises(FeedError, match=problem):
        parse_daily(content)


class FixtureFrench:
    """TEST FIXTURE: stands in for the library download."""

    def __init__(self, rows):
        self.rows = rows

    def daily_market(self):
        return self.rows, Provenance(
            "Kenneth R. French Data Library", "https://fixture.test/ff.zip", NOW, "end_of_day"
        )


def test_stores_once_and_keeps_old_values_when_the_library_revises(engine):
    rows = [(date(2020, 1, 1), 0.01, 0.0001), (date(2020, 1, 2), -0.02, 0.0001)]
    assert run_market_history(engine, FixtureFrench(rows)) == "ok"
    assert run_market_history(engine, FixtureFrench(rows)) == "ok"  # Nothing new.
    revised = [rows[0], (date(2020, 1, 2), -0.019, 0.0001)]
    run_market_history(engine, FixtureFrench(revised))
    with engine.connect() as conn:
        stored = (
            conn.execute(
                text(
                    """SELECT value FROM factor_returns WHERE series = 'mkt_rf'
                   AND market_date = '2020-01-02' ORDER BY id"""
                )
            )
            .scalars()
            .all()
        )
        source = conn.execute(
            text(
                """SELECT f.source_url FROM factor_returns r JOIN fetches f ON f.id = r.fetch_id
                   LIMIT 1"""
            )
        ).scalar()
    assert stored == [-0.02, -0.019]
    assert source == "https://fixture.test/ff.zip"


def test_trend_rule_waits_for_200_days_and_never_looks_ahead():
    rng = np.random.default_rng(3)
    excess = pd.Series(
        rng.normal(0.0003, 0.01, 1500), index=pd.bdate_range("1990-01-01", periods=1500)
    )
    level = (1 + excess).cumprod()
    out = studies.trend_returns(studies.trend_on(level), excess)
    assert out.index[0] == excess.index[200]  # Decided at day 199's close, held from day 200.
    cut = 900
    changed = excess.copy()
    changed.iloc[cut + 1 :] *= -3
    again = studies.trend_returns(studies.trend_on((1 + changed).cumprod()), changed)
    pd.testing.assert_series_equal(out.iloc[: cut - 199], again.iloc[: cut - 199])


def test_century_study_runs_end_to_end_and_stores_every_version(engine):
    from stockintel.quant import run

    rng = np.random.default_rng(8)
    days = pd.bdate_range("1960-01-01", "2026-09-30")
    vol = np.array([0.006, 0.01, 0.02])[(np.arange(len(days)) // 250) % 3]
    rows = [
        (d.date(), float(r), 0.0001)
        for d, r in zip(days, rng.normal(0.0003, 1, len(days)) * vol, strict=True)
    ]
    run_market_history(engine, FixtureFrench(rows))
    run.market_century(engine, None, None)
    with engine.connect() as conn:
        variants = (
            conn.execute(
                text("SELECT variant FROM quant_results WHERE study = 'market_century' ORDER BY id")
            )
            .scalars()
            .all()
        )
    assert variants == [label for _, label in run.CENTURY_VERSIONS] + ["trend 50/200"]
