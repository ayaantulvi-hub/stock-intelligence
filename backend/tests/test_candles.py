"""Candlestick rules. Every candle here is a TEST FIXTURE."""

from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockintel import candles, horizons, misses


def bars(rows):
    start = date(2026, 1, 1)
    table = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    table["market_date"] = [start + timedelta(days=i) for i in range(len(table))]
    table["volume"] = 100.0
    return table


def falling(n=10, start=120.0):
    return [(start - i, start - i + 0.2, start - i - 1.2, start - i - 1) for i in range(n)]


def rising(n=10, start=100.0):
    return [(start + i, start + i + 1.2, start + i - 0.2, start + i + 1) for i in range(n)]


def last(rows):
    return {key for key, value in candles.detect(bars(rows)).iloc[-1].items() if value}


def test_every_pattern_has_a_rule_and_the_rules_match_the_list():
    frame = candles.detect(bars(falling(15)))
    assert set(frame.columns) == set(candles.BY_ID)
    assert len(candles.BY_ID) >= 34


def test_hammer_needs_a_fall_first_and_hanging_man_a_rise():
    shape = (100.0, 100.7, 96.0, 100.6)
    assert "hammer" in last([*falling(10, 112), shape])
    assert "hanging_man" in last([*rising(10, 90), shape])


def test_shooting_star():
    assert "shooting_star" in last([*rising(10, 90), (100.0, 104.0, 99.9, 100.6)])


def test_engulfing_both_ways():
    down = falling(10, 112)
    assert "bull_engulfing" in last(
        [*down, (102.0, 102.2, 100.8, 101.0), (100.8, 103.2, 100.7, 103.0)]
    )
    up = rising(10, 90)
    assert "bear_engulfing" in last([*up, (100.0, 101.2, 99.9, 101.0), (101.2, 101.3, 98.8, 99.0)])


def test_morning_star_three_candles():
    rows = [
        *falling(10, 115),
        (105.0, 105.1, 100.9, 101.0),
        (100.0, 100.4, 99.6, 99.8),
        (100.5, 104.2, 100.4, 104.0),
    ]
    assert "morning_star" in last(rows)


def test_three_white_soldiers_and_black_crows():
    soldiers = [
        *falling(10, 115),
        (100.0, 102.1, 99.9, 102.0),
        (101.0, 103.1, 100.9, 103.0),
        (102.0, 104.1, 101.9, 104.0),
    ]
    assert "white_soldiers" in last(soldiers)
    crows = [
        *rising(10, 95),
        (106.0, 106.1, 103.9, 104.0),
        (105.0, 105.1, 102.9, 103.0),
        (104.0, 104.1, 101.9, 102.0),
    ]
    assert "black_crows" in last(crows)


def test_detection_never_uses_later_candles():
    rng = np.random.default_rng(1)
    close = 100 + rng.normal(0, 1, 200).cumsum()
    table = bars([(c - 0.3, c + 1, c - 1, c + rng.normal(0, 0.5)) for c in close])
    full = candles.detect(table)
    cut = candles.detect(table.iloc[:150])
    assert full.iloc[:150].equals(cut)


def test_study_measures_against_all_stocks_after_costs():
    rng = np.random.default_rng(2)
    close = 100 + rng.normal(0, 1, 800).cumsum() / 3 + 50
    table = bars([(c, c + 1, c - 1, c + rng.normal(0, 1)) for c in close])
    results = candles.study({"AAA": table})
    assert results
    assert {row["horizon"] for row in results} == {1, 5}
    for row in results:
        assert 0 <= row["win_rate"] <= 1


def test_proven_needs_size_strength_and_the_right_sign():
    good = {"signals": 100, "t_stat": 3.5, "extra_return": 0.01}
    assert candles.proven(good)
    assert not candles.proven({**good, "signals": 5})
    assert not candles.proven({**good, "t_stat": 2.0})
    assert not candles.proven({**good, "extra_return": -0.01})
    assert not candles.proven(None)


def hammer_day():
    return bars([*falling(20, 122), (100.0, 100.7, 96.0, 100.6)])


def test_trade_is_unproven_until_tested_and_gives_exits():
    answer = horizons.trade(hammer_day(), {}, False, None)
    assert answer["call"] == "Leans buy, short trade"
    assert answer["hold"] == 5
    assert answer["stop"] < 100.6 < answer["target"]
    tested = {"hammer": {"signals": 100, "win_rate": 0.6, "extra_return": 0.01, "t_stat": 4.0}}
    assert horizons.trade(hammer_day(), tested, False, None)["call"] == "Buy for a short trade"


def test_a_pattern_that_failed_testing_gives_no_trade():
    failed = {"hammer": {"signals": 100, "win_rate": 0.4, "extra_return": -0.01, "t_stat": -1.0}}
    assert horizons.trade(hammer_day(), failed, False, None)["call"] == horizons.NO_TRADE


def test_no_trade_when_stale_or_results_are_due():
    assert horizons.trade(hammer_day(), {}, True, None)["call"] == "Wait"
    assert horizons.trade(hammer_day(), {}, False, 1)["call"] == horizons.NO_TRADE


def lens(name, verdict):
    return {"name": name, "verdict": verdict}


def test_invest_answer_follows_the_company_checks():
    names = horizons.LONG_LENSES
    good = {"lenses": [lens(name, "good") for name in names], "blocked": None}
    assert horizons.invest(good)["call"] == "Good to buy and keep"
    bad = {"lenses": [lens(name, "bad") for name in names], "blocked": None}
    assert horizons.invest(bad)["call"] == "Not a long-term buy"
    assert horizons.invest({**good, "blocked": "x"})["call"] == "Avoid for now"
    blank = {"lenses": [lens(name, "unknown") for name in names], "blocked": None}
    assert horizons.invest(blank)["call"] == "Not verified"


def test_miss_reasons_put_the_strongest_evidence_first():
    assert misses.reason(-0.05, -0.04, 0.01, -0.02, None, ["2.02,9.01"]) == misses.RESULTS
    assert misses.reason(-0.02, -0.001, 0.015, -0.015, None, []) == misses.MARKET
    assert misses.reason(-0.03, -0.001, 0.015, 0.001, -0.02, []) == misses.INDUSTRY
    assert misses.reason(0.05, 0.04, 0.01, 0.001, None, []) == misses.GAP
    assert misses.reason(0.05, 0.001, 0.01, 0.001, None, []) == misses.UNKNOWN
    assert misses.reason(0.005, 0.001, 0.01, 0.001, None, []) == misses.NOISE
    assert misses.reason(-0.03, 0.0, 0.01, 0.0, None, ["4.02"]).startswith("Company filing")
