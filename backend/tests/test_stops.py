"""Stops. Every price series here is a TEST FIXTURE."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stockintel import queries, stops
from stockintel.backtest import assert_no_look_ahead


def frame(closes, spread=1.0):
    closes = np.asarray(closes, float)
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(len(closes))]
    return pd.DataFrame(
        {
            "market_date": days,
            "open": closes,
            "high": closes + spread,
            "low": closes - spread,
            "close": closes,
            "volume": 1.0,
        }
    )


def test_true_range_counts_overnight_gaps():
    table = frame([100, 100, 110])
    assert stops.average_true_range(table, 1).iloc[2] == 11


def test_stop_defaults_to_three_daily_ranges():
    table = frame([100.0] * 40)
    result = stops.suggest(table)
    assert result["atr"] == 2
    assert result["stop"] == 94
    assert result["target"] == 112


def test_target_is_twice_the_risk():
    result = stops.suggest(frame([100.0] * 40))
    assert result["target"] - result["price"] == pytest.approx(
        2 * (result["price"] - result["stop"])
    )


def test_stop_sits_under_support_when_it_is_close():
    wave = []
    for _ in range(4):
        wave += [90 + i for i in range(10)] + [100 - i for i in range(10)]
    table = frame([*wave, *[92.0] * 8], spread=0.5)
    result = stops.suggest(table)
    assert "floor" in result["stop_reason"]
    assert result["stop"] < 90


def test_short_history_gives_nothing():
    assert stops.suggest(frame([100.0] * 5)) is None


def test_gap_below_the_stop_fills_at_the_open_not_the_stop():
    closes = [100.0] * 16 + [50.0] * 70
    trades = stops.simulate(frame(closes), 2.0)
    assert trades[0][1] is True
    assert trades[0][0] == pytest.approx(50 / 100 - 1 - stops.COST)


def test_no_stop_holds_to_the_end():
    closes = [100.0] * 16 + [50.0] * 70
    trades = stops.simulate(frame(closes), None)
    assert trades[0][1] is False


def test_tighter_stops_trigger_more_often():
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 1500)))
    table = frame(closes, spread=1.0)
    tight = stops.study({1.5: stops.simulate(table, 1.5)})[0]
    wide = stops.study({4.0: stops.simulate(table, 4.0)})[0]
    assert tight["stopped_share"] > wide["stopped_share"]


def test_stop_uses_no_future_prices():
    rng = np.random.default_rng(1)
    table = frame(100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300))))
    assert_no_look_ahead(
        lambda f: stops.average_true_range(f).round(9).to_frame().fillna(-1), table
    )


def test_ineligible_days_are_skipped():
    table = frame([100.0] * 200)
    assert stops.simulate(table, 2.0, np.zeros(200, bool)) == []


def test_unknown_stock(engine):
    assert queries.suggested_levels(engine, "ZZZ") is None
