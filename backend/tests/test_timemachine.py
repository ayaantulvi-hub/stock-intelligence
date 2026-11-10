"""Time Machine and opening-range breakout. Every bar here is a TEST FIXTURE."""

from datetime import date, time

import numpy as np
import pandas as pd

from stockintel import orb, timemachine


def session(day, closes):
    times = pd.date_range(f"{day} 09:30", periods=len(closes), freq="5min", tz="America/New_York")
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame(
        {
            "time": times,
            "open": opens,
            "high": np.maximum(opens, closes) + 0.01,
            "low": np.minimum(opens, closes) - 0.01,
            "close": closes,
            "volume": 1e5,
        }
    )


def test_only_full_earlier_sessions_go_in_the_pool():
    full = session("2026-11-02", np.linspace(100, 101, 78))
    short = session("2026-11-03", np.linspace(100, 101, 40))
    today = session("2026-11-04", np.linspace(100, 101, 78))
    days = timemachine.sessions(pd.concat([full, short, today]), date(2026, 11, 4))
    assert len(days) == 1


def test_steady_rises_hit_the_target_and_the_seed_repeats():
    days = [
        session(f"2026-10-{d:02d}", 100 * 1.001 ** np.arange(78)).iloc[:, 1:5].to_numpy()
        for d in range(1, 25)
    ]
    ratios = timemachine.pool(days)
    first = timemachine.simulate(ratios, 100, 99, 101, 10, 76, long=True, replays=2000)
    again = timemachine.simulate(ratios, 100, 99, 101, 10, 76, long=True, replays=2000)
    assert first == again
    assert first["p_target"] > 0.99
    assert "Strongly toward the target" in timemachine.verdict(first)
    short = timemachine.simulate(ratios, 100, 101, 99, 10, 76, long=False, replays=2000)
    assert short["p_stop"] > 0.99


def test_coin_flip_verdict_uses_break_even():
    mc = {"p_target": 0.40, "p_stop": 0.42, "p_neither": 0.18, "r_at_target": 1.0}
    assert timemachine.verdict(mc).startswith("Close to a coin flip")
    two_r = {"p_target": 0.30, "p_stop": 0.60, "p_neither": 0.10, "r_at_target": 2.0}
    assert timemachine.verdict(two_r).startswith("Close to break-even")


def test_opening_range_breakout_rule():
    closes = [100, 101, 99.5] + [100.5] * 3 + [102] + [102.5] * 71
    bars = session("2026-11-04", closes)[["open", "high", "low", "close"]].to_numpy()
    plan = orb.setup(bars)
    assert plan["long"] and plan["bar"] == 6 and plan["entry"] == 102
    middle = (bars[:3, 1].max() + bars[:3, 2].min()) / 2
    assert plan["stop"] == middle
    assert plan["target"] == 102 + 2 * (102 - middle)
    assert orb.setup(bars, upto=5) is None  # Not yet broken at that point.


def test_stop_is_counted_first_when_both_are_touched():
    bars = np.array([[100, 101, 99, 100]] * 3 + [[100, 102, 100, 101.5], [101.5, 110, 90, 101]])
    plan = orb.setup(bars)
    assert orb.outcome(bars, plan, 4)["result"] == "stop"


def test_backtest_skips_short_days_and_compares_with_chance():
    rng = np.random.default_rng(2)
    days = [
        session(f"2026-10-{d:02d}", 100 + np.cumsum(rng.normal(0, 0.2, 78))) for d in range(1, 21)
    ]
    days.append(session("2026-10-21", np.linspace(100, 101, 50)))
    rows = orb.backtest({"AAA": pd.concat(days, ignore_index=True)})
    assert 0 < len(rows) <= 20
    assert all(row["entered"].time() <= time(15, 30) for row in rows)
    assert all("random_r" in row for row in rows)


def test_runs_of_bars_keep_streaks_that_single_bars_break():
    up = [session(f"2026-10-{d:02d}", 100 * 1.003 ** np.arange(78)) for d in range(1, 13)]
    down = [session(f"2026-10-{d:02d}", 100 * 0.997 ** np.arange(78)) for d in range(13, 25)]
    ratios = timemachine.pool([d.iloc[:, 1:5].to_numpy() for d in up + down])
    runs = timemachine.simulate(ratios, 100, 50, 200, 10, 76, long=True, replays=3000, block=6)
    single = timemachine.simulate(ratios, 100, 50, 200, 10, 76, long=True, replays=3000)
    assert runs["close_high"] - runs["close_low"] > 2 * (single["close_high"] - single["close_low"])


def daily(closes):
    closes = np.asarray(closes, dtype=float)
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame(
        {
            "market_date": pd.bdate_range("2024-01-01", periods=len(closes)).date,
            "open": opens,
            "high": np.maximum(opens, closes) * 1.005,
            "low": np.minimum(opens, closes) * 0.995,
            "close": closes,
        }
    )


def test_a_steady_riser_gains_in_almost_every_replay():
    result = timemachine.hold(daily(100 * 1.002 ** np.arange(400)), stop=50.0)
    assert result["p_gain"] > 0.99 and result["p_stop"] == 0
    assert result["record"]["p_gain"] == 1.0
    assert result["verdict"].startswith("Leans toward a gain")


def test_the_stop_caps_losses_and_counts_in_the_replays():
    falling = daily(100 * 0.995 ** np.arange(400))
    entry = float(falling["close"].iloc[-1])
    result = timemachine.hold(falling, stop=entry * 0.95)
    assert result["p_stop"] > 0.9
    assert result["low"] >= -0.06  # A gap can sell a little below the stop, not far.


def test_too_little_history_gives_no_replay():
    assert timemachine.hold(daily(100 + np.arange(100)), stop=90.0) is None


def test_replays_repeat_with_the_same_seed():
    frame = daily(100 + np.cumsum(np.random.default_rng(3).normal(0, 1, 400)))
    first = timemachine.hold(frame, stop=None)
    assert first == timemachine.hold(frame, stop=None)


def test_default_matches_the_original_one_bar_at_a_time():
    assert timemachine.BLOCK == 1


def test_original_notes_when_many_replays_hit_neither():
    mc = {"p_target": 0.2, "p_stop": 0.1, "p_neither": 0.7, "r_at_target": 1.0, "avg_r": -0.05}
    notes = timemachine.verdict_notes(mc)
    assert notes[0].startswith("70.0% of the replays hit neither")
    assert "Average R is -0.050 all the same" in notes[1]
