"""Opening-range breakout, as in trader-scanner and trader-exit from
github.com/Jakeschincariol/day-trader-skill (MIT licence).

The range is the first 15 minutes. A setup is the first 5-minute bar after the range to close
above the range high (buy) or below the range low (sell short), no later than 15:30. The stop
is the range midpoint and the target is 2 times the risk (trader-exit's defaults). Out by 15:55.
"""

from datetime import time

import numpy as np
import pandas as pd

RANGE_BARS = 3  # 15 minutes of 5-minute bars.
LAST_ENTRY = time(15, 30)
FLAT_BY = time(15, 55)
TARGET_R = 2.0
MIN_PRICE = 5.0
COST = 0.0002  # The same 0.02% each way used for the TJR test.


def setup(day: np.ndarray, upto: int | None = None) -> dict | None:
    """First breakout in one session of (open, high, low, close) rows. `upto` limits the bars."""
    if len(day) <= RANGE_BARS:
        return None
    high, low = day[:RANGE_BARS, 1].max(), day[:RANGE_BARS, 2].min()
    last_entry = (LAST_ENTRY.hour * 60 + LAST_ENTRY.minute - 570) // 5 - 1
    end = min(len(day) - 1, last_entry if upto is None else min(upto, last_entry))
    for i in range(RANGE_BARS, end + 1):
        close = day[i, 3]
        if close > high or close < low:
            long = close > high
            entry, stop = float(close), float((high + low) / 2)
            risk = entry - stop if long else stop - entry
            if risk <= 0:
                return None
            target = entry + TARGET_R * risk if long else entry - TARGET_R * risk
            return {
                "bar": i,
                "long": long,
                "entry": entry,
                "stop": stop,
                "target": target,
                "range_high": float(high),
                "range_low": float(low),
            }
    return None


def outcome(day: np.ndarray, plan: dict, last: int) -> dict:
    """Stop first, then target, bar by bar after the entry, else the close at `last`."""
    long, entry, stop, target = plan["long"], plan["entry"], plan["stop"], plan["target"]
    risk = abs(entry - stop)
    result, exit_price = "close", float(day[min(last, len(day) - 1), 3])
    for row in day[plan["bar"] + 1 : last + 1]:
        if (row[2] <= stop) if long else (row[1] >= stop):
            result, exit_price = "stop", stop
            break
        if (row[1] >= target) if long else (row[2] <= target):
            result, exit_price = "target", target
            break
    move = exit_price - entry if long else entry - exit_price
    return {"result": result, "r": (move - COST * (entry + exit_price)) / risk}


def history(days: list[np.ndarray], last: int) -> dict:
    """The rule on every past session: what really happened."""
    trades = []
    for day in days:
        plan = setup(day)
        if plan is not None:
            trades.append(outcome(day, plan, last))
    rs = [t["r"] for t in trades]
    return {
        "sessions": len(days),
        "triggered": len(trades),
        "target": sum(t["result"] == "target" for t in trades),
        "stop": sum(t["result"] == "stop" for t in trades),
        "avg_r": float(np.mean(rs)) if rs else None,
    }


def backtest(frames: dict[str, pd.DataFrame]) -> list[dict]:
    """Every session of every stock, for the 3-year test. Frames hold 5-minute bars."""
    last = (FLAT_BY.hour * 60 + FLAT_BY.minute - 570) // 5 - 1
    rng = np.random.default_rng(0)
    rows = []
    for symbol, frame in frames.items():
        regular = frame[(frame["time"].dt.time >= time(9, 30)) & (frame["time"].dt.time < time(16))]
        for day, group in regular.groupby(regular["time"].dt.date):
            bars = group[["open", "high", "low", "close"]].to_numpy(dtype=float)
            if len(bars) != 78 or bars[RANGE_BARS - 1, 3] < MIN_PRICE:
                continue
            plan = setup(bars)
            if plan is None:
                continue
            result = outcome(bars, plan, last)
            flipped = dict(plan, long=not plan["long"])
            risk = abs(plan["entry"] - plan["stop"])
            flipped["stop"] = plan["entry"] + risk if plan["long"] else plan["entry"] - risk
            flipped["target"] = (
                plan["entry"] - TARGET_R * risk if plan["long"] else plan["entry"] + TARGET_R * risk
            )
            chance = outcome(bars, flipped if rng.random() < 0.5 else plan, last)
            rows.append(
                {
                    "symbol": symbol,
                    "entered": group["time"].iloc[plan["bar"]],
                    "confirmed_by": "close beyond range",
                    "level": "opening range",
                    "r": result["r"],
                    "random_r": chance["r"],
                    "outcome": result["result"],
                }
            )
    return rows
