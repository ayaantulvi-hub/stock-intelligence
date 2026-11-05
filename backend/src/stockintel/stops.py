"""Suggested stop and target prices, and a test of stop distances.

A stop can't be known to be best in advance. These levels follow a stated rule based on how
much the stock usually moves, and the study shows how each distance would have done.

Run: python -m stockintel.stops
"""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel.backtest import eligibility, eligible_days
from stockintel.charts import levels
from stockintel.db import get_engine

ATR_DAYS = 14
# Tested weekly. Tighter stops were hit far more often and cut returns, so 3 is the default.
DEFAULT_MULTIPLE = 3.0
REWARD_TO_RISK = 2.0
HOLD_DAYS = 20
ENTRY_EVERY = 20
MULTIPLES = (None, 1.5, 2.0, 3.0, 4.0)
COST = 0.001


def average_true_range(frame: pd.DataFrame, days: int = ATR_DAYS) -> pd.Series:
    """The typical full daily range, including overnight gaps."""
    previous = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous).abs(),
            (frame["low"] - previous).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return ranges.rolling(days).mean()


def suggest(frame: pd.DataFrame, multiple: float = DEFAULT_MULTIPLE) -> dict | None:
    """A stop just under support if that is sensible, otherwise a set distance below."""
    if len(frame) <= ATR_DAYS:
        return None
    price = float(frame["close"].iloc[-1])
    atr = float(average_true_range(frame).iloc[-1])
    if np.isnan(atr) or atr <= 0:
        return None
    found = {level.kind: level.price for level in levels(frame)}
    distance_stop = price - multiple * atr
    support = found.get("support")
    below_support = None if support is None else support * 0.99
    near = below_support is not None and price - 3 * atr <= below_support <= price - atr
    stop = below_support if near else distance_stop
    risk = price - stop
    target = price + REWARD_TO_RISK * risk
    resistance = found.get("resistance")
    return {
        "price": price,
        "atr": atr,
        "stop": stop,
        "target": target,
        "risk_percent": risk / price * 100,
        "target_percent": (target / price - 1) * 100,
        "stop_reason": (
            f"Just under the floor at {support:.2f}, where it has stopped falling before."
            if near
            else f"{multiple:.0f} times its typical daily range of {atr:.2f} below the price, "
            "so normal swings are less likely to trigger it."
        ),
        "target_reason": f"Aims to make {REWARD_TO_RISK:.0f} times what the stop risks.",
        "ceiling_warning": (
            f"There is a ceiling at {resistance:.2f} before this target."
            if resistance is not None and price < resistance < target
            else None
        ),
    }


def simulate(
    frame: pd.DataFrame, multiple: float | None, eligible: np.ndarray | None = None
) -> list[tuple[float, bool]]:
    """Buy at the next open on regular dates and hold, exiting early at the stop.

    Each stop is set from data known at entry. A gap below the stop fills at the open.
    """
    opens = frame["open"].to_numpy(float)
    lows = frame["low"].to_numpy(float)
    closes = frame["close"].to_numpy(float)
    atr = average_true_range(frame).to_numpy(float)
    trades = []
    for day in range(ATR_DAYS, len(frame) - HOLD_DAYS - 1, ENTRY_EVERY):
        if np.isnan(atr[day]) or (eligible is not None and not eligible[day]):
            continue
        entry = opens[day + 1]
        stop = None if multiple is None else entry - multiple * atr[day]
        leave, stopped = closes[day + 1 + HOLD_DAYS - 1], False
        if stop is not None:
            for step in range(day + 1, day + 1 + HOLD_DAYS):
                if lows[step] <= stop:
                    leave, stopped = min(opens[step], stop), True
                    break
        trades.append((leave / entry - 1 - COST, stopped))
    return trades


def study(results: dict) -> list[dict]:
    output = []
    for multiple, trades in results.items():
        if not trades:
            continue
        returns = np.array([item[0] for item in trades])
        output.append(
            {
                "stop_multiple": multiple,
                "trades": len(trades),
                "avg_return": float(returns.mean()),
                "win_rate": float((returns > 0).mean()),
                "worst_return": float(returns.min()),
                "stopped_share": float(np.mean([item[1] for item in trades])),
            }
        )
    return output


def run(engine: Engine) -> list[dict]:
    # Imported here so the website does not load the machine-learning libraries.
    from stockintel.forecast import load_frames

    sizes = eligibility(engine)
    with engine.connect() as conn:
        ciks = dict(conn.execute(text("SELECT ticker, cik FROM securities")).all())
    results: dict = {multiple: [] for multiple in MULTIPLES}
    for ticker, frame in load_frames(engine).items():
        allowed = eligible_days(frame["market_date"], sizes.get(ciks[ticker], set()))
        for multiple in MULTIPLES:
            results[multiple].extend(simulate(frame, multiple, allowed))
    rows = study(results)
    now = datetime.now(UTC)
    if rows:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO stop_studies (run_at, stop_multiple, trades, avg_return,
                         win_rate, worst_return, stopped_share)
                       VALUES (:now, :stop_multiple, :trades, :avg_return, :win_rate,
                         :worst_return, :stopped_share)"""
                ),
                [{**row, "now": now} for row in rows],
            )
    for row in rows:
        print(row)
    return rows


if __name__ == "__main__":
    run(get_engine())
