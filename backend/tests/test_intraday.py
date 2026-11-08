"""Day trading rules. Every bar here is a TEST FIXTURE, built by hand."""

from datetime import date

import pandas as pd

from stockintel import intraday

NY = "America/New_York"


def bars(rows, start="2026-11-09 09:30"):
    """Rows of (open, high, low, close), one minute apart."""
    times = pd.date_range(start, periods=len(rows), freq="1min", tz=NY)
    frame = pd.DataFrame(rows, columns=["open", "high", "low", "close"])
    frame.insert(0, "time", times)
    frame["volume"] = 1000.0
    return frame


def test_swing_high_is_known_only_after_the_down_candle():
    frame = bars([(1, 2, 0.5, 1.5), (1.5, 3, 1, 2.5), (2.5, 2.8, 1.8, 2), (2, 2.2, 1.5, 1.6)])
    assert (2, "high", 3.0) in intraday.swings(frame)
    assert intraday.last_swing(intraday.swings(frame), "high", 2) is None
    assert intraday.last_swing(intraday.swings(frame), "high", 3) == 3.0


def test_break_of_structure_needs_a_close_not_a_wick():
    rows = [(10, 11, 9.5, 10.5), (10.5, 12, 10, 11), (11, 11.5, 10.2, 10.4), (10.4, 13, 10.3, 11.9)]
    frame = bars(rows)
    assert intraday.break_of_structure(frame, 3) is None  # Wick to 13, close 11.9 below 12.
    frame = bars([*rows[:3], (10.4, 12.5, 10.3, 12.2)])
    assert intraday.break_of_structure(frame, 3) == "bullish"


def test_fair_value_gap_and_its_inverse():
    rows = [(10, 10.2, 9.9, 10.1), (10.1, 11, 10.1, 10.9), (10.9, 11.3, 10.6, 11.2)]
    frame = bars(rows)
    assert intraday.gaps(frame, 2)[0].side == "bullish"
    assert (intraday.gaps(frame, 2)[0].low, intraday.gaps(frame, 2)[0].high) == (10.2, 10.6)
    frame = bars([*rows, (11.2, 11.2, 10.4, 10.5), (10.5, 10.6, 10, 10.1)])
    assert intraday.inverse_gap(frame, 4) == "bearish"


def test_smt_when_one_index_makes_a_higher_high_and_the_other_does_not():
    up = [
        (1, 2, 0.9, 1.9),
        (1.9, 2, 1.5, 1.6),
        (1.6, 1.7, 1.4, 1.65),
        (1.65, 2.5, 1.6, 2.4),
        (2.4, 2.45, 2, 2.1),
    ]
    lower = [
        (1, 2, 0.9, 1.9),
        (1.9, 2, 1.5, 1.6),
        (1.6, 1.7, 1.4, 1.65),
        (1.65, 1.9, 1.6, 1.8),
        (1.8, 1.85, 1.5, 1.6),
    ]
    assert intraday.smt(bars(up), bars(lower), 4) == "bearish"
    assert intraday.smt(bars(up), bars(up), 4) is None


def test_key_levels_use_only_earlier_prices():
    yesterday = bars(
        [(100, 101 + i % 3, 99 - i % 2, 100)[:4] for i in range(390)], "2026-11-06 09:30"
    )
    early = bars([(100, 100.5, 99.8, 100)] * 30, "2026-11-09 08:00")
    later = bars([(100, 150, 50, 100)] * 30, "2026-11-09 09:30")
    history = pd.concat([yesterday, early, later], ignore_index=True)
    levels = intraday.key_levels(history, date(2026, 11, 9))
    assert levels["Previous day high"] == 103
    assert levels["Previous day low"] == 98
    assert levels["Pre-market high"] == 100.5
    assert 150 not in levels.values() and 50 not in levels.values()


def test_trade_result_in_risk_units_after_costs():
    trade = intraday.Trade("SPY", "short", "x", "y", None, 100.0, 101.0, 98.0)
    trade.exit = 98.0
    assert round(trade.r, 3) == round((2 - 0.0002 * 198) / 1, 3)


def test_exit_assumes_the_stop_first_when_both_are_touched():
    trade = intraday.Trade("SPY", "long", "x", "y", None, 100.0, 99.0, 102.0)
    after = bars([(100, 102.5, 98.5, 101)], "2026-11-09 10:00")
    assert intraday._exit(trade, after).result == "stop"


def test_no_trades_outside_the_window():
    flat = bars([(100, 100.1, 99.9, 100)] * 60, "2026-11-09 11:00")
    assert intraday.scan_day("SPY", flat, flat, {"Previous day high": 100.05}) == []


def test_backtest_runs_on_two_days_and_compares_with_chance():
    import numpy as np

    rng = np.random.default_rng(1)

    def day(start, n=390):
        steps = np.cumsum(rng.normal(0, 0.05, n)) + 100
        rows = [(c, c + 0.08, c - 0.08, c + rng.normal(0, 0.03)) for c in steps]
        return bars(rows, start)

    frames = {}
    for symbol in ("SPY", "QQQ"):
        frame = pd.concat([day("2026-11-05 09:30"), day("2026-11-06 09:30")], ignore_index=True)
        frames[symbol] = frame
    rows = intraday.backtest(frames)
    for row in rows:
        assert row["entered"].time() < intraday.WINDOW[1]
        assert "random_r" in row
