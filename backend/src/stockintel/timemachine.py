"""Time Machine: 10,000 replays of the rest of a trading day, and the rule's real record.

Adapted from trader-timemachine in github.com/Jakeschincariol/day-trader-skill (MIT licence,
copyright Jake Schincariol), using Alpaca bars instead of Yahoo. Same method:

1. The pool: full past sessions (78 five-minute bars, 9:30 to 16:00 New York time). Each bar
   becomes four ratios to the bar before it: open, high, low and close over the previous close.
2. One replay starts at the entry price and scales past bars to the current price. Changed
   from the original, which drew every bar on its own: here it draws runs of 6 bars (30
   minutes) in a row from one past day, from the same time of day plus or minus 2 bars. Real
   prices run in streaks, and drawing bars one at a time breaks them, pushing every answer
   towards a coin flip. The stop is checked before the target, so a bar touching both counts
   as the stop.
3. The verdict compares how often the target came first, among replays that hit one side,
   with the share needed to break even: 1 in (1 + R).

It is a simulation built from the stock's own recent bars, not a prediction.
"""

from datetime import time

import numpy as np
import pandas as pd

SESSION_BARS = 78
MIN_SESSIONS = 20
REPLAYS = 10_000
SEED = 19
WINDOW = 2
BLOCK = 6  # Bars drawn in a row from one past day.
COIN_FLIP = 0.05
STRONG = 0.15


def sessions(bars: pd.DataFrame, before) -> list[np.ndarray]:
    """Full regular sessions before a date, each an array of (open, high, low, close) rows."""
    regular = bars[(bars["time"].dt.time >= time(9, 30)) & (bars["time"].dt.time < time(16))]
    found = []
    for day, group in regular.groupby(regular["time"].dt.date):
        if day >= before or len(group) != SESSION_BARS:
            continue
        found.append(group[["open", "high", "low", "close"]].to_numpy(dtype=float))
    return found


def pool(days: list[np.ndarray]) -> np.ndarray:
    """pool[slot, day] = that day's bar as ratios to the previous close. Slot 0 is unused."""
    out = np.full((SESSION_BARS, len(days), 4), np.nan)
    for d, day in enumerate(days):
        out[1:, d, :] = day[1:, :] / day[:-1, 3:4]
    return out


def simulate(
    ratios: np.ndarray,
    entry,
    stop,
    target,
    after: int,
    last: int,
    long: bool,
    replays: int = REPLAYS,
    seed: int = SEED,
    block: int = BLOCK,
) -> dict:
    """Replay bars after+1 .. last. Returns the odds and the average R."""
    rng = np.random.default_rng(seed)
    risk = (entry - stop) if long else (stop - entry)
    r_target = ((target - entry) if long else (entry - target)) / risk
    price = np.full(replays, float(entry))
    outcome = np.zeros(replays, dtype=int)  # 0 open, 1 target, -1 stop
    days = ratios.shape[1]
    for step, bar in enumerate(range(after + 1, last + 1)):
        if step % block == 0:
            shift = rng.integers(-WINDOW, WINDOW + 1, replays)
            day = rng.integers(0, days, replays)
        slots = np.clip(bar + shift, 1, SESSION_BARS - 1)
        picks = ratios[slots, day]
        high, low, close = price * picks[:, 1], price * picks[:, 2], price * picks[:, 3]
        live = outcome == 0
        hit_stop = live & ((low <= stop) if long else (high >= stop))
        hit_target = live & ~hit_stop & ((high >= target) if long else (low <= target))
        outcome[hit_stop], outcome[hit_target] = -1, 1
        price = close
    move = (price - entry) if long else (entry - price)
    r = np.where(outcome == 1, r_target, np.where(outcome == -1, -1.0, move / risk))
    return {
        "replays": replays,
        "p_target": float((outcome == 1).mean()),
        "p_stop": float((outcome == -1).mean()),
        "p_neither": float((outcome == 0).mean()),
        "avg_r": float(r.mean()),
        "r_at_target": float(r_target),
        "close_low": float(np.percentile(price, 5)),
        "close_high": float(np.percentile(price, 95)),
    }


def verdict(mc: dict) -> str:
    hit = mc["p_target"] + mc["p_stop"]
    if hit <= 0:
        return "No replay reached the target or the stop. The closing price decides every one."
    share, even = mc["p_target"] / hit, 1 / (1 + mc["r_at_target"])
    gap = share - even
    if abs(gap) < COIN_FLIP:
        head = (
            "Close to a coin flip" if abs(mc["r_at_target"] - 1) < 0.005 else "Close to break-even"
        )
    elif abs(gap) < STRONG:
        head = "Leans toward the target" if gap > 0 else "Leans toward the stop"
    else:
        head = "Strongly toward the target" if gap > 0 else "Strongly toward the stop"
    return (
        f"{head}: target first in {mc['p_target']:.0%} of replays, stop first in "
        f"{mc['p_stop']:.0%}. To break even the target needs to come first in {even:.0%} of "
        f"those that hit one, and it did in {share:.0%}."
    )


def bar_index(when: pd.Timestamp) -> int:
    """The 5-minute bar a New York time falls in, counting 9:30 as bar 0."""
    return (when.hour * 60 + when.minute - 570) // 5


def run(
    bars: pd.DataFrame,
    day,
    entry_time: pd.Timestamp,
    entry,
    stop,
    target,
    long: bool,
    flat_by: time,
    history=None,
) -> dict | None:
    """The replays for one plan. `history` re-runs a rule on each past session."""
    days = sessions(bars, day)
    if len(days) < MIN_SESSIONS:
        return None
    after = bar_index(entry_time)
    last = bar_index(pd.Timestamp.combine(day, flat_by)) - 1
    if last <= after:
        return None
    mc = simulate(pool(days), entry, stop, target, after, last, long)
    mc["sessions"] = len(days)
    mc["verdict"] = verdict(mc)
    if history is not None:
        mc["history"] = history(days, last)
    return mc


# The same idea for holds of about a month, on daily candles.
DAILY_HISTORY = 504  # About two years of trading days.
HOLD_DAYS = 20
DAILY_BLOCK = 5  # Draw a week of days in a row, so streaks carry through.
MIN_DAILY = 250


def daily_ratios(frame: pd.DataFrame) -> np.ndarray:
    """Each day as open, high, low and close over the day before's close, from adjusted bars."""
    recent = frame.tail(DAILY_HISTORY + 1)
    values = recent[["open", "high", "low", "close"]].to_numpy(dtype=float)
    return values[1:] / values[:-1, 3:4]


def simulate_hold(
    ratios: np.ndarray,
    entry: float,
    stop: float | None,
    days: int = HOLD_DAYS,
    replays: int = REPLAYS,
    seed: int = SEED,
    block: int = DAILY_BLOCK,
) -> dict:
    """Replay the next `days` trading days 10,000 times from the stock's own past days.

    A replay picks a random past week and plays its days in order, then another, scaled to the
    current price. A day whose low reaches the stop sells at the stop, or at the open if it
    opened below it. Otherwise the replay sells at the last day's close."""
    rng = np.random.default_rng(seed)
    price = np.full(replays, float(entry))
    exit_price = np.full(replays, np.nan)
    start = rng.integers(0, len(ratios) - block, replays)
    for step in range(days):
        if step % block == 0:
            start = rng.integers(0, len(ratios) - block, replays)
        day = ratios[start + step % block]
        open_, low, close = price * day[:, 0], price * day[:, 2], price * day[:, 3]
        live = np.isnan(exit_price)
        if stop is not None:
            hit = live & (low <= stop)
            exit_price[hit] = np.minimum(open_[hit], stop)
        price = close
    stopped = ~np.isnan(exit_price)
    final = np.where(stopped, exit_price, price)
    change = final / entry - 1
    return {
        "replays": replays,
        "days": days,
        "p_stop": float(stopped.mean()),
        "p_gain": float((change > 0).mean()),
        "median": float(np.median(change)),
        "average": float(change.mean()),
        "low": float(np.percentile(change, 5)),
        "high": float(np.percentile(change, 95)),
    }


def hold_record(frame: pd.DataFrame, days: int = HOLD_DAYS) -> dict:
    """What really happened: every past `days`-day hold over the same two years."""
    close = frame["close"].tail(DAILY_HISTORY + days).to_numpy(dtype=float)
    ahead = close[days:] / close[:-days] - 1
    return {
        "holds": len(ahead),
        "p_gain": float((ahead > 0).mean()) if len(ahead) else None,
        "median": float(np.median(ahead)) if len(ahead) else None,
    }


def hold_verdict(mc: dict) -> str:
    if mc["p_gain"] >= 0.6:
        head = "Leans toward a gain"
    elif mc["p_gain"] <= 0.4:
        head = "Leans toward a loss"
    else:
        head = "Close to a coin flip"
    return (
        f"{head}: {mc['p_gain']:.0%} of replays ended up, {mc['p_stop']:.0%} hit the stop, "
        f"and 9 in 10 ended between {mc['low']:+.0%} and {mc['high']:+.0%}."
    )


def hold(frame: pd.DataFrame, stop: float | None, days: int = HOLD_DAYS) -> dict | None:
    """Replays and the real record for holding from today's close for `days` trading days."""
    if len(frame) < MIN_DAILY:
        return None
    entry = float(frame["close"].iloc[-1])
    mc = simulate_hold(daily_ratios(frame), entry, stop, days)
    mc.update(entry=entry, stop=stop, verdict=hold_verdict(mc), record=hold_record(frame, days))
    return mc
