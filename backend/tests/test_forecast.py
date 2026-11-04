"""Forecasts and the ledger. All prices here are TEST FIXTURES, generated from fixed seeds."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from stockintel import factors, forecast, queries
from stockintel.backtest import assert_no_look_ahead
from stockintel.market import session_close, sessions_between


def stock(seed, length=1300, end=date(2026, 7, 7)):
    rng = np.random.default_rng(seed)
    days = sessions_between(end - timedelta(days=length * 2), end)[-length:]
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.018, len(days))))
    return pd.DataFrame(
        {
            "market_date": days,
            "open": closes * 0.999,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": rng.uniform(5e5, 2e6, len(days)),
        }
    )


@pytest.fixture(scope="module")
def panel():
    frames = {f"S{seed}": stock(seed) for seed in range(30)}
    days = pd.date_range("2015-01-01", "2026-07-08", freq="D")
    slope = pd.Series(np.random.default_rng(0).normal(0.5, 0.5, len(days)), index=days)
    return forecast.build_panel(frames, slope)


def test_missing_yield_data_blocks_forecasts():
    with pytest.raises(RuntimeError, match="blocked"):
        forecast.build_panel({"S1": stock(1, 400)}, None)


def test_market_readings_are_used_only_from_when_they_were_public():
    days = pd.date_range("2024-01-01", periods=3, freq="D")
    macro = pd.DataFrame({"vix": [10.0, 20.0, 30.0]}, index=days + pd.Timedelta(days=1))
    panel_ = forecast.build_panel(
        {"S1": stock(1, 400, date(2024, 1, 10))},
        pd.Series(1.0, index=pd.date_range("2022-01-01", "2024-02-01")),
        None,
        macro,
    )
    first = panel_[panel_["date"] == pd.Timestamp("2024-01-02")]["vix"].iloc[0]
    assert first == 10.0


def test_ineligible_rows_are_left_out_of_training(panel, monkeypatch):
    blocked = panel.assign(eligible=False)
    assert forecast.walk_forward(blocked, first_year=2025) == []
    assert forecast.test_factors(blocked) == []


def test_sector_ranks_compare_within_an_industry():
    frames = {f"S{seed}": stock(seed, 400) for seed in range(4)}
    slope = pd.Series(1.0, index=pd.date_range("2024-01-01", "2026-07-08"))
    table = forecast.build_panel(
        frames, slope, None, None, {"S0": 35, "S1": 35, "S2": 60, "S3": 60}
    )
    latest = table[table["date"] == table["date"].max()]
    assert set(latest["sector_momentum"].dropna()) <= {0.5, 1.0}


def test_every_factor_names_a_source():
    for item in factors.REGISTER:
        assert item.source
        assert item.status


def test_quoted_effects_have_a_link():
    for item in factors.REGISTER:
        if item.effect:
            assert item.url


def test_factors_that_need_missing_data_are_marked_and_not_used():
    assert "news_sentiment" not in factors.LIVE_IDS
    assert "implied_move" not in factors.LIVE_IDS
    assert "value" in factors.LIVE_IDS


def test_filing_is_not_used_before_it_was_public():
    frame = stock(3, 500).assign(raw_close=lambda f: f["close"])
    filed = pd.Timestamp(frame["market_date"].iloc[300]) + pd.Timedelta(days=1)
    company = {
        "filings": pd.DataFrame(
            {
                "available": [filed],
                "equity": [1000.0],
                "profitability": [0.4],
                "investment": [0.1],
                "accruals": [0.0],
                "income_change": [0.1],
            }
        ),
        "shares": pd.DataFrame({"available": [filed], "shares": [10.0]}),
        "trades": pd.DataFrame(),
    }
    table = pd.DataFrame(index=frame.index)
    forecast.add_company_data(table, frame, company)
    assert table["profitability"].iloc[:301].isna().all()
    assert table["profitability"].iloc[302] == 0.4
    assert table["value"].iloc[302] == pytest.approx(1000 / (frame["close"].iloc[302] * 10))


def test_quarters_with_gaps_do_not_break_the_panel():
    frame = stock(3, 500).assign(raw_close=lambda f: f["close"])
    day = pd.Timestamp(frame["market_date"].iloc[300])
    quarters = pd.DataFrame(
        {"available": [day], "income_q": pd.Series([None], dtype=object), "revenue_q": [0.1]}
    )
    table = pd.DataFrame(index=frame.index)
    table["earnings_drift"] = np.nan
    forecast.add_company_data(table, frame, {"quarters": quarters})
    assert table["revenue_growth"].iloc[301] == 0.1


def test_insider_net_value_counts_buys_as_positive():
    trades = pd.DataFrame(
        {
            "filed": [date(2026, 1, 2), date(2026, 1, 3)],
            "code": ["P", "S"],
            "shares": [10.0, 4.0],
            "price": [2.0, 5.0],
        }
    )
    assert list(forecast.insider_values(trades)["net_value"]) == [20.0, -20.0]


def test_factors_do_not_look_ahead():
    assert_no_look_ahead(lambda f: factors.stock_factors(f).round(10).fillna(-999), stock(1, 600))


@pytest.mark.parametrize(
    "change, expected",
    [(0.002, "up"), (-0.002, "down"), (0.0005, "flat"), (-0.0005, "flat")],
)
def test_outcome_bands(change, expected):
    assert forecast.outcome(change) == expected


def test_random_prices_earn_no_edge(panel):
    results = forecast.walk_forward(panel, first_year=2024)
    assert {item.model for item in results} == {"next_day", "rank_20d"}
    assert not any(item.edge for item in results)


def test_training_never_includes_the_test_year(panel, monkeypatch):
    seen = []
    real = forecast.model

    class Spy:
        def __init__(self):
            self.inner = real()

        def fit(self, x, y):
            seen.append(panel.loc[x.index, "date"].max())
            self.inner.fit(x, y)
            return self.inner

    monkeypatch.setattr(forecast, "model", Spy)
    forecast.walk_forward(panel, first_year=2025)
    assert seen and max(seen) < pd.Timestamp(2026, 1, 1)
    assert seen[0] < pd.Timestamp(2025, 1, 1)


def seed_security(engine, ticker="S1"):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES (:t, 1, 'Fixture', 'NYSE', 1)"""
            ),
            {"t": ticker},
        )


LEDGER = """INSERT INTO forecasts (created_at, security_id, as_of_session, target_session,
    target_close, last_close, p_up, p_flat, p_down, range_low, range_high, next_day_edge,
    rank_edge, confidence, drivers)
    VALUES (:created, 1, '2026-07-06', '2026-07-07', :close, 100, .5, .1, .4, 95, 105,
    false, false, 'None', '[]')"""


def add_row(engine, created):
    with engine.begin() as conn:
        conn.execute(text(LEDGER), {"created": created, "close": session_close(date(2026, 7, 7))})


def test_forecast_after_the_outcome_is_refused(engine):
    seed_security(engine)
    with pytest.raises(DBAPIError, match="before its outcome"):
        add_row(engine, datetime(2026, 7, 8, tzinfo=UTC))


@pytest.mark.parametrize("statement", ["UPDATE forecasts SET p_up = 0.9", "DELETE FROM forecasts"])
def test_ledger_cannot_be_edited(engine, statement):
    seed_security(engine)
    add_row(engine, datetime(2026, 7, 7, 1, tzinfo=UTC))
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text(statement))


def add_bar(engine, day, close, split=1.0, dividend=0.0):
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
                   WHERE name = 'Tiingo' RETURNING id"""
            )
        ).scalar()
        conn.execute(
            text(
                """INSERT INTO price_bars (security_id, fetch_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (1, :f, :d, now(), :c, :c, :c, :c, 1, :div, :split)"""
            ),
            {"f": fetch, "d": day, "c": close, "div": dividend, "split": split},
        )


def test_forecast_is_scored_when_the_close_arrives(engine):
    seed_security(engine)
    add_row(engine, datetime(2026, 7, 7, 1, tzinfo=UTC))
    assert forecast.score_forecasts(engine) == 0
    add_bar(engine, "2026-07-06", 100)
    add_bar(engine, "2026-07-07", 102)
    assert forecast.score_forecasts(engine) == 1
    assert forecast.score_forecasts(engine) == 0
    with engine.connect() as conn:
        score = conn.execute(text("SELECT * FROM forecast_scores")).first()
    assert score.outcome == "up"
    assert score.in_range is True
    assert score.brier == pytest.approx(0.25 + 0.01 + 0.16)


def test_split_on_the_target_day_is_not_a_crash(engine):
    seed_security(engine)
    add_row(engine, datetime(2026, 7, 7, 1, tzinfo=UTC))
    add_bar(engine, "2026-07-06", 100)
    add_bar(engine, "2026-07-07", 51, split=2.0)
    forecast.score_forecasts(engine)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT outcome FROM forecast_scores")).scalar() == "up"


def test_writes_no_edge_forecasts_with_real_range(engine, panel):
    seed_security(engine)
    now = datetime(2026, 7, 8, 12, tzinfo=UTC)
    assert forecast.write_forecasts(engine, panel[panel["ticker"].isin(["S1", "S2"])], now) == 1
    row = queries.stock_forecast(engine, "S1")
    assert row["target_session"] == date(2026, 7, 8)
    assert row["next_day_edge"] is False
    assert row["confidence"] == "None"
    assert row["p_up"] + row["p_flat"] + row["p_down"] == pytest.approx(1)
    assert row["range_low"] < row["last_close"] < row["range_high"]
    assert len(row["drivers"]) == 15
    assert row["action"] == "No reliable edge"


def test_stale_prices_block_forecasts(engine, panel):
    seed_security(engine)
    with pytest.raises(RuntimeError, match="blocked as stale"):
        forecast.write_forecasts(engine, panel, datetime(2026, 8, 4, 12, tzinfo=UTC))


def test_no_forecast_once_the_market_has_opened(engine, panel):
    seed_security(engine)
    with pytest.raises(RuntimeError, match="already open"):
        forecast.write_forecasts(engine, panel, datetime(2026, 7, 8, 15, tzinfo=UTC))


def test_ideas_name_no_stocks_without_an_edge(engine, panel):
    seed_security(engine)
    forecast.write_forecasts(engine, panel, datetime(2026, 7, 8, 12, tzinfo=UTC))
    result = queries.ideas(engine)
    assert result["edge"] is False
    assert result["buy"] == [] and result["sell"] == []


def test_confidence_is_none_without_an_edge():
    chances = {"up": 0.9, "flat": 0.05, "down": 0.05}
    assert forecast.confidence(False, chances, chances) == "None"


@pytest.mark.parametrize(
    "edge, rank, expected",
    [
        (False, 0.99, "No reliable edge"),
        (True, 0.95, "Buy candidate"),
        (True, 0.05, "Sell candidate"),
        (True, 0.5, "No action"),
        (True, None, "No reliable edge"),
    ],
)
def test_action_needs_a_tested_edge(edge, rank, expected):
    assert queries.action(edge, rank) == expected


def test_factor_tests_report_spread_and_strength(panel):
    results = forecast.test_factors(panel)
    assert {"vol_20", "reversal_5d"} <= {row["factor"] for row in results}
    assert not any(abs(row["t_stat"]) > 6 for row in results)  # Random fixture data.


def test_screener_lists_each_stock_with_its_lean(engine, panel):
    seed_security(engine)
    forecast.write_forecasts(engine, panel, datetime(2026, 7, 8, 12, tzinfo=UTC))
    rows = queries.screener(engine)
    assert [row["ticker"] for row in rows] == ["S1"]
    assert rows[0]["action"] == "No reliable edge"
    assert rows[0]["lean"] in {"Buy", "Mixed", "Sell"}
