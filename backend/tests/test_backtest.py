"""Backtest rules. All price series here are TEST FIXTURES, generated or hand-written."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel import charts, queries
from stockintel.backtest import (
    COST_BPS,
    Backtest,
    LookAheadError,
    Tally,
    assert_no_look_ahead,
    calibration,
    has_edge,
    run,
)
from stockintel.charts import detect_patterns, pattern_history


def random_frame(length=700, seed=5):
    rng = np.random.default_rng(seed)
    closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.02, length)))
    opens = closes * (1 + rng.normal(0, 0.008, length))
    days = [date(2019, 1, 1) + timedelta(days=i) for i in range(length)]
    return pd.DataFrame(
        {
            "market_date": days,
            "open": opens,
            "high": np.maximum(opens, closes) * 1.005,
            "low": np.minimum(opens, closes) * 0.995,
            "close": closes,
            "volume": 1000.0,
        }
    )


def planted_look_ahead(frame):
    """Deliberately cheats: true today if tomorrow's close is higher."""
    return pd.DataFrame({"cheat": frame["close"].shift(-1) > frame["close"]})


def test_planted_look_ahead_is_caught():
    with pytest.raises(LookAheadError):
        assert_no_look_ahead(planted_look_ahead, random_frame())


def test_real_signals_pass_the_look_ahead_check():
    assert_no_look_ahead(pattern_history, random_frame())


def test_adjusting_for_later_events_cannot_change_past_signals():
    frame = random_frame().assign(div_cash=0.0, split_factor=1.0)
    frame.loc[650, "div_cash"] = 3.0
    frame.loc[680, "split_factor"] = 4.0
    frame.loc[680:, ["open", "high", "low", "close"]] /= 4
    full = pattern_history(charts.adjust(frame))
    partial = pattern_history(charts.adjust(frame.iloc[:600].reset_index(drop=True)))
    pd.testing.assert_frame_equal(full.iloc[:600], partial)


def test_history_matches_the_live_rules_on_every_candle():
    frame = random_frame(420)
    history = pattern_history(frame)
    for end in range(205, len(frame)):
        live = {
            (item.name, item.direction)
            for item in detect_patterns(frame.iloc[: end + 1].reset_index(drop=True))
            if item.state == "confirmed" and item.name not in {"Breakout", "Breakdown"}
        }
        assert live == {key for key, value in history.iloc[end].items() if value}


def trades(frame, name, direction, horizon):
    test = Backtest(cost_bps=0)
    test.add_stock(frame)
    return test.signals[(name, direction, horizon)]


def test_trade_enters_at_the_next_open_not_the_signal_close():
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(10)]
    opens = [100, 100, 100, 97.5, 110, 110, 110, 110, 110, 110]
    closes = [100, 100, 98, 103, 110, 110, 110, 110, 110, 121]
    frame = pd.DataFrame(
        {
            "market_date": days,
            "open": opens,
            "close": closes,
            "high": [c + 9 for c in closes],
            "low": [c - 9 for c in closes],
            "volume": 1.0,
        }
    )
    tally = trades(frame, "Bullish engulfing", "bullish", 5)[2024]
    assert tally.count == 1
    assert tally.total == pytest.approx(121 / 110 - 1)  # Not 121 / 103 - 1.


def test_costs_reduce_every_trade():
    frame = random_frame()
    gross = Backtest(cost_bps=0)
    net = Backtest(cost_bps=COST_BPS)
    gross.add_stock(frame)
    net.add_stock(frame)
    before = gross.signals[("MACD cross", "bullish", 5)][2019]
    after = net.signals[("MACD cross", "bullish", 5)][2019]
    assert after.count == before.count
    assert after.total == pytest.approx(before.total - before.count * COST_BPS / 10000)


def test_bearish_signal_wins_when_the_price_falls():
    frame = random_frame()
    test = Backtest(cost_bps=0)
    test.add_stock(frame)
    up = test.baselines[("bullish", 5)][2019]
    down = test.baselines[("bearish", 5)][2019]
    assert up.total == pytest.approx(-down.total)


def tally(wins, count, average):
    return Tally(wins=wins, count=count, total=average * count)


def test_edge_needs_enough_cases():
    assert not has_edge(tally(20, 20, 0.05), tally(500, 1000, 0.01))


def test_edge_needs_more_than_a_small_lead():
    assert not has_edge(tally(52, 100, 0.02), tally(500, 1000, 0.01))


def test_edge_needs_a_better_average_return():
    assert not has_edge(tally(70, 100, 0.005), tally(500, 1000, 0.01))


def test_clear_lead_counts_as_an_edge():
    assert has_edge(tally(70, 100, 0.03), tally(500, 1000, 0.01))


def test_random_prices_show_no_edge():
    test = Backtest()
    for seed in range(12):
        test.add_stock(random_frame(1500, seed))
    assert not [row for row in test.results() if row["edge"]]


def test_baseline_is_reported_with_every_result():
    test = Backtest()
    test.add_stock(random_frame())
    for row in test.results():
        assert row["baseline_win_rate"] is not None
        assert row["baseline_avg_return"] is not None


def test_a_later_good_year_cannot_be_used_before_it_happens():
    test = Backtest(cost_bps=0)
    good, plain = tally(90, 100, 0.05), tally(500, 1000, 0.0)
    test.signals[("Rule", "bullish", 20)][2020] = tally(50, 100, 0.0)
    test.signals[("Rule", "bullish", 20)][2021] = good
    test.baselines[("bullish", 20)][2020] = plain
    test.baselines[("bullish", 20)][2021] = tally(500, 1000, 0.0)
    row = test.results()[0]
    assert row["sample_size"] == 200
    assert row["oos_sample_size"] == 0  # 2021 was never approved by earlier years.
    assert row["edge"] is False


def test_calibration_compares_stated_chances_with_results():
    table = calibration([(0.7, True), (0.7, True), (0.7, False), (0.1, False)])
    assert table[0] == {"stated": 0.1, "actual": 0.0, "count": 1}
    assert table[1]["actual"] == pytest.approx(2 / 3)


def test_run_stores_results_and_warns_about_survivorship(engine):
    frame = random_frame(800)
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('AAA', 1, 'Fixture', 'NYSE', 1)"""
            )
        )
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
                   VALUES (1, :fetch, :market_date, now(), :open, :high, :low, :close,
                     :volume, 0, 1)"""
            ),
            [{**row, "fetch": fetch} for row in frame.to_dict("records")],
        )
    run(engine)
    latest = queries.latest_backtest(engine)
    assert latest["stocks"] == 1
    assert "Survivorship" in latest["note"]
    assert latest["results"]
    assert "Golden cross:bullish" in queries.records_for(engine, "daily")
    assert queries.records_for(engine, "weekly") == {}


def test_no_backtest_yet_returns_nothing(engine):
    assert queries.latest_backtest(engine) is None
    assert queries.records_for(engine, "daily") == {}
