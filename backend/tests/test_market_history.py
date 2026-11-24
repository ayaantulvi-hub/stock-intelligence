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
from stockintel.providers.french import FILES, MIN_ROWS, parse_columns, parse_daily
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
        (_zip(["no header here"] + _rows(MIN_ROWS)), "no Mkt-RF, RF column"),
        (_zip([",Mkt-RF,SMB"] + _rows(MIN_ROWS)), "no RF column"),
    ],
)
def test_broken_files_raise_instead_of_storing_bad_data(content, problem):
    with pytest.raises(FeedError, match=problem):
        parse_daily(content)


class FixtureFrench:
    """TEST FIXTURE: stands in for the library download. Market rows are (day, mkt_rf, rf);
    other files return `extra` rows of (day, {series: value}) or fail with `error`."""

    def __init__(self, rows, extra=None, error=None):
        self.rows, self.extra, self.error = rows, extra or {}, error

    def daily(self, name):
        if name == self.error:
            raise FeedError("French library: HTTP 503")
        if name == "market":
            rows = [(d, {"mkt_rf": m, "rf": r}) for d, m, r in self.rows]
        else:
            rows = self.extra.get(name, [])
        return rows, Provenance(
            "Kenneth R. French Data Library", f"https://fixture.test/{name}.zip", NOW, "end_of_day"
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
    assert source == "https://fixture.test/market.zip"


def test_one_failing_file_is_reported_and_the_others_still_load(engine):
    rows = [(date(2020, 1, 1), 0.01, 0.0001)]
    extra = {"us five factors": [(date(2020, 1, 1), {"us_smb": 0.002})]}
    status = run_market_history(engine, FixtureFrench(rows, extra, error="developed ex US"))
    assert status == "partial"
    with engine.connect() as conn:
        names = set(conn.execute(text("SELECT DISTINCT series FROM factor_returns")).scalars())
    assert names == {"mkt_rf", "rf", "us_smb"}


def test_reads_named_columns_from_other_factor_files():
    lines = [",SMB,HML,RMW,CMA,RF"] + [
        f"{d:%Y%m%d},0.20,-0.10,0.05,0.01,0.01"
        for d in pd.bdate_range("1963-07-01", periods=10_000)
    ]
    rows = parse_columns(_zip(lines), FILES["us five factors"][1], 10_000)
    assert rows[0][1] == {
        "us_smb": pytest.approx(0.002),
        "us_hml": pytest.approx(-0.001),
        "us_rmw": pytest.approx(0.0005),
        "us_cma": pytest.approx(0.0001),
    }


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


def _factors(seed: int = 4) -> pd.DataFrame:
    """TEST FIXTURE: three invented factors; one starts later than the others."""
    rng = np.random.default_rng(seed)
    days = pd.bdate_range("2000-01-03", "2006-12-29")
    f = pd.DataFrame(rng.normal(0, 0.005, (len(days), 3)), index=days, columns=["a", "b", "c"])
    f["a"] += 0.0008  # Always rising: should always be held long.
    f["b"] -= 0.0008  # Always falling: should always be held short.
    f.loc[:"2003-06-30", "c"] = np.nan  # Joins only after a full year of its own history.
    return f


def test_factor_momentum_goes_with_each_factors_past_year():
    returns, held = studies.factor_momentum(_factors())
    assert returns.index[0] > pd.Timestamp("2001-01-01")  # Needs 12 months first.
    late = held.loc["2006"]
    assert (late["a"] == 1).all() and (late["b"] == -1).all()
    assert held.loc[:"2004-06-30", "c"].isna().all()  # c started mid-2003: no full year yet.
    assert held.loc["2004-08":, "c"].notna().all()


def test_factor_momentum_uses_only_the_past():
    factors = _factors()
    returns, _ = studies.factor_momentum(factors)
    changed = factors.copy()
    cut = changed.index.get_loc(pd.Timestamp("2004-03-15"))
    changed.iloc[cut + 1 :] *= -5
    again, _ = studies.factor_momentum(changed)
    pd.testing.assert_series_equal(
        returns.loc[: factors.index[cut]], again.loc[: factors.index[cut]]
    )


def test_factor_momentum_charges_for_each_flip():
    factors = _factors()
    free, _ = studies.factor_momentum(factors, cost_bps=0)
    paid, held = studies.factor_momentum(factors, cost_bps=10)
    flips_cost = (free - paid).sum()
    assert flips_cost > 0
    # Costs fall only on days a position changes: entering, flipping, or a factor joining.
    changed = held.fillna(0).diff().abs().sum(axis=1)
    changed.iloc[0] = held.iloc[0].abs().sum()
    assert (free - paid)[(free - paid) > 1e-12].index.isin(changed.index[changed > 0]).all()
