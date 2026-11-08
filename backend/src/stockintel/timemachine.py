"""Time Machine: 10,000 replays of the rest of a trading day, and the rule's real record.

Adapted from trader-timemachine in github.com/Jakeschincariol/day-trader-skill (MIT licence,
copyright Jake Schincariol), using Alpaca bars instead of Yahoo. Same method:

1. The pool: full past sessions (78 five-minute bars, 9:30 to 16:00 New York time). Each bar
   becomes four ratios to the bar before it: open, high, low and close over the previous close.
2. One replay starts at the entry price. For each remaining bar it draws a past bar from the
   same time of day (plus or minus 2 bars) and scales it to the current price. The stop is
   checked before the target, so a bar touching both counts as the stop.
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
) -> dict:
    """Replay bars after+1 .. last. Returns the odds and the average R."""
    rng = np.random.default_rng(seed)
    risk = (entry - stop) if long else (stop - entry)
    r_target = ((target - entry) if long else (entry - target)) / risk
    price = np.full(replays, float(entry))
    outcome = np.zeros(replays, dtype=int)  # 0 open, 1 target, -1 stop
    days = ratios.shape[1]
    for bar in range(after + 1, last + 1):
        slots = np.clip(bar + rng.integers(-WINDOW, WINDOW + 1, replays), 1, SESSION_BARS - 1)
        picks = ratios[slots, rng.integers(0, days, replays)]
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
