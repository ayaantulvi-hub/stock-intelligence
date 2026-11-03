"""Indicators against TA-Lib, an independent reference. Tolerance: 1e-6 in price or points.

The price series here are TEST FIXTURES generated from a fixed seed, not market data.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
import talib

from stockintel import charts
from stockintel.charts import Level, Pattern, adjust, detect_patterns, levels, resample, summary
from stockintel.market import sessions_between
from stockintel.signals import TestedRecord, build_signals, label

TOLERANCE = 1e-6


@pytest.fixture
def closes():
    steps = np.random.default_rng(7).normal(0.0005, 0.02, 600)
    return pd.Series(100 * np.exp(np.cumsum(steps)))


def same(ours, reference):
    ours, reference = np.asarray(ours, float), np.asarray(reference, float)
    assert np.array_equal(np.isnan(ours), np.isnan(reference))
    assert np.nanmax(np.abs(ours - reference)) < TOLERANCE


def test_sma_matches_talib(closes):
    same(charts.sma(closes, 50), talib.SMA(closes.to_numpy(), 50))


def test_ema_matches_talib(closes):
    same(charts.ema(closes, 20), talib.EMA(closes.to_numpy(), 20))


def test_rsi_matches_talib(closes):
    same(charts.rsi(closes), talib.RSI(closes.to_numpy(), 14))


def test_macd_matches_talib(closes):
    line, signal, histogram = talib.MACD(closes.to_numpy())
    ours = charts.macd(closes).iloc[33:]
    same(ours["macd"], line[33:])
    same(ours["signal"], signal[33:])
    same(ours["histogram"], histogram[33:])


def bars(rows):
    days = sessions_between(date(2026, 1, 2), date(2026, 12, 31))[: len(rows)]
    return pd.DataFrame(
        [
            {
                "market_date": day,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": v,
                "div_cash": d,
                "split_factor": s,
            }
            for day, (c, v, d, s) in zip(days, rows, strict=True)
        ]
    )


def test_split_makes_prices_continuous():
    frame = adjust(bars([(100, 10, 0, 1), (100, 10, 0, 1), (50, 20, 0, 2), (50, 20, 0, 1)]))
    assert list(frame["close"]) == [50, 50, 50, 50]
    assert list(frame["volume"]) == [20, 20, 20, 20]


def test_dividend_lowers_earlier_prices_only():
    frame = adjust(bars([(100, 10, 0, 1), (100, 10, 2, 1), (100, 10, 0, 1)]))
    assert frame["close"].iloc[0] == pytest.approx(98)
    assert frame["close"].iloc[1] == 100
    assert list(frame["volume"]) == [10, 10, 10]


def candles(days, closes=None):
    closes = closes if closes is not None else [100 + i for i in range(len(days))]
    return pd.DataFrame(
        {
            "market_date": days,
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
            "volume": [1] * len(days),
        }
    )


def test_weekly_candle_combines_the_week_and_skips_holidays():
    days = sessions_between(date(2026, 6, 29), date(2026, 7, 10))  # 3 July is closed.
    weekly = resample(candles(days), "weekly")
    assert list(weekly["market_date"]) == [date(2026, 7, 2), date(2026, 7, 10)]
    assert weekly["open"].iloc[0] == 100
    assert weekly["close"].iloc[0] == 103
    assert weekly["high"].iloc[0] == 104
    assert weekly["volume"].iloc[0] == 4


def test_unfinished_week_is_left_out():
    days = sessions_between(date(2026, 7, 6), date(2026, 7, 15))
    assert list(resample(candles(days), "weekly")["market_date"]) == [date(2026, 7, 10)]


def test_monthly_candle_uses_complete_months_only():
    days = sessions_between(date(2026, 5, 1), date(2026, 7, 8))
    monthly = resample(candles(days), "monthly")
    assert list(monthly["market_date"]) == [date(2026, 5, 29), date(2026, 6, 30)]


def frame_of(closes, opens=None):
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(len(closes))]
    opens = opens if opens is not None else closes
    return pd.DataFrame(
        {
            "market_date": days,
            "open": opens,
            "close": closes,
            "high": [max(o, c) + 0.5 for o, c in zip(opens, closes, strict=True)],
            "low": [min(o, c) - 0.5 for o, c in zip(opens, closes, strict=True)],
            "volume": [1.0] * len(closes),
        }
    )


def named(frame, name):
    return [p for p in detect_patterns(frame) if p.name == name]


def test_golden_cross_fires_on_the_crossing_candle_only():
    closes = [100.0] * 200 + [90.0] * 50
    closes += [120.0] * 200
    series = pd.Series(closes)
    short, long = charts.sma(series, 50), charts.sma(series, 200)
    cross = next(
        i for i in range(201, len(closes)) if short[i - 1] <= long[i - 1] and short[i] > long[i]
    )
    assert named(frame_of(closes[: cross + 1]), "Golden cross")[0].state == "confirmed"
    assert not [
        p for p in named(frame_of(closes[: cross + 2]), "Golden cross") if p.state == "confirmed"
    ]
    assert named(frame_of(closes[: cross + 1]), "Golden cross")[
        0
    ].cancellation_level == pytest.approx(long[cross])


def test_death_cross_mirrors_golden_cross():
    closes = [100.0] * 200 + [110.0] * 50 + [80.0] * 200
    series = pd.Series(closes)
    short, long = charts.sma(series, 50), charts.sma(series, 200)
    cross = next(
        i for i in range(201, len(closes)) if short[i - 1] >= long[i - 1] and short[i] < long[i]
    )
    assert named(frame_of(closes[: cross + 1]), "Death cross")[0].direction == "bearish"


def test_cross_that_is_close_shows_as_forming():
    closes = [100.0] * 200 + [90.0] * 50 + [120.0] * 200
    series = pd.Series(closes)
    short, long = charts.sma(series, 50), charts.sma(series, 200)
    cross = next(
        i for i in range(201, len(closes)) if short[i - 1] <= long[i - 1] and short[i] > long[i]
    )
    forming = named(frame_of(closes[:cross]), "Golden cross")
    assert forming and forming[0].state == "forming"


def test_bullish_engulfing():
    frame = frame_of([100, 100, 98, 103], opens=[100, 100, 100, 97.5])
    pattern = named(frame, "Bullish engulfing")[0]
    assert pattern.direction == "bullish"
    assert pattern.cancellation_level == 97.0


def test_bearish_engulfing():
    frame = frame_of([100, 100, 102, 97], opens=[100, 100, 100, 102.5])
    assert named(frame, "Bearish engulfing")[0].direction == "bearish"


def test_up_candle_inside_the_last_one_is_not_engulfing():
    assert not named(frame_of([100, 100, 98, 99], opens=[100, 100, 100, 98.5]), "Bullish engulfing")


def test_rsi_recovery_needs_a_move_back_above_30():
    falling = [100 - i for i in range(30)]
    assert not named(frame_of(falling), "RSI recovery")
    assert named(frame_of([*falling, 79.0]), "RSI recovery")


def test_rsi_rollover_needs_a_move_back_below_70():
    rising = [100 + i for i in range(30)]
    assert named(frame_of([*rising, 120.0]), "RSI rollover")


def test_macd_cross_fires_when_the_histogram_changes_sign(closes):
    histogram = charts.macd(closes)["histogram"]
    cross = next(i for i in range(40, len(closes)) if histogram[i - 1] <= 0 < histogram[i])
    assert named(frame_of(list(closes[: cross + 1])), "MACD cross")[0].direction == "bullish"
    assert not named(frame_of(list(closes[: cross + 2])), "MACD cross")


def wave():
    """Price peaks twice near 110, with troughs near 90, then sits at 100."""
    closes = []
    for _ in range(3):
        closes += [90 + i * 2 for i in range(10)] + [110 - i * 2 for i in range(10)]
    return closes + [100.0] * 8


def test_levels_find_clustered_turning_points():
    found = {level.kind: level for level in levels(frame_of(wave()))}
    assert found["resistance"].touches >= 2
    assert 107 < found["resistance"].price < 112
    assert 87 < found["support"].price < 93


def test_breakout_is_confirmed_above_resistance():
    frame = frame_of([*wave(), 115.0])
    pattern = named(frame, "Breakout")[0]
    assert (pattern.state, pattern.direction) == ("confirmed", "bullish")


def test_breakdown_is_confirmed_below_support():
    assert named(frame_of([*wave(), 85.0]), "Breakdown")[0].direction == "bearish"


def pattern(state="confirmed", direction="bullish"):
    return Pattern("Golden cross", direction, state, date(2026, 7, 7), 95.0, "fixture")


def test_untested_signal_is_unproven_never_bullish():
    assert label(pattern(), None) == "Unproven"
    assert label(pattern(), TestedRecord(10, 0.9, 0.5, True)) == "Unproven"


def test_forming_label():
    assert label(pattern("forming"), TestedRecord(100, 0.9, 0.5, True)) == "Forming"


def test_labels_follow_the_tested_record():
    assert label(pattern(), TestedRecord(100, 0.6, 0.5, True)) == "Bullish"
    assert label(pattern(direction="bearish"), TestedRecord(100, 0.6, 0.5, True)) == "Bearish"
    assert label(pattern(), TestedRecord(100, 0.6, 0.5, False)) == "Neutral"


def test_signal_shows_record_sample_and_cancellation():
    signal = build_signals([pattern()], {})[0]
    assert signal["label"] == "Unproven"
    assert signal["sample_size"] == 0
    assert signal["win_rate"] is None
    assert signal["cancellation_level"] == 95.0


def test_summary_states_plain_facts():
    frame = frame_of([100.0 + i for i in range(250)])
    result = summary(frame, [Level("resistance", 349 * 1.1, 2), Level("support", 349 * 0.9, 2)])
    assert result["close"] == 349
    assert result["change_percent"] == pytest.approx(1 / 348 * 100)
    assert result["above_50"] is True
    assert result["above_200"] is True
    assert result["rsi_state"] == "Overbought"
    assert result["percent_to_resistance"] == pytest.approx(10)
    assert result["percent_to_support"] == pytest.approx(-10)


def test_summary_leaves_unknown_values_blank():
    result = summary(frame_of([100.0, 101.0]), [])
    assert result["above_200"] is None
    assert result["rsi_state"] is None
    assert result["percent_to_resistance"] is None
