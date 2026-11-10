"""Which Time Machine predicts better: drawing each 5-minute bar on its own (the original
day-trader-skill method) or drawing 30-minute runs from one past day?

For every opening-range breakout in the test stocks, each version replays the rest of the day
using only the 60 sessions before it, and says how likely the target, the stop or neither is.
Then the real day decides. The score is the Brier score over the three outcomes: lower is
better. A plain baseline uses how often each outcome happened in earlier setups only.

Run: python -m stockintel.tm_eval [stocks] [months]
"""

import sys
from datetime import UTC, datetime, time

import numpy as np
import pandas as pd

from stockintel import orb, timemachine
from stockintel.day_trading import fetch, provider, universe

POOL_DAYS = 60
REPLAYS = 2000
VERSIONS = {"Original: one bar at a time": 1, "30-minute runs": 6}


def sessions(frame: pd.DataFrame) -> list[np.ndarray]:
    regular = frame[(frame["time"].dt.time >= time(9, 30)) & (frame["time"].dt.time < time(16))]
    out = []
    for _, group in regular.groupby(regular["time"].dt.date):
        bars = group[["open", "high", "low", "close"]].to_numpy(dtype=float)
        if len(bars) == timemachine.SESSION_BARS:
            out.append(bars)
    return out


def brier(p: np.ndarray, outcome: np.ndarray) -> np.ndarray:
    """Per-setup Brier score over target, stop and neither."""
    actual = np.eye(3)[outcome]
    return ((p - actual) ** 2).sum(axis=1)


def evaluate(days_by_stock: dict[str, list[np.ndarray]]) -> dict:
    last = timemachine.bar_index(pd.Timestamp("2026-01-02 15:55")) - 1
    rows = []
    for days in days_by_stock.values():
        for n in range(POOL_DAYS, len(days)):
            plan = orb.setup(days[n])
            if plan is None:
                continue
            result = orb.outcome(days[n], plan, last)["result"]
            outcome = {"target": 0, "stop": 1, "close": 2}[result]
            ratios = timemachine.pool(days[n - POOL_DAYS : n])
            row = {"outcome": outcome}
            for name, block in VERSIONS.items():
                mc = timemachine.simulate(
                    ratios,
                    plan["entry"],
                    plan["stop"],
                    plan["target"],
                    plan["bar"],
                    last,
                    plan["long"],
                    replays=REPLAYS,
                    block=block,
                )
                row[name] = (mc["p_target"], mc["p_stop"], mc["p_neither"])
            rows.append(row)
    if not rows:
        return {"setups": 0}
    outcomes = np.array([r["outcome"] for r in rows])
    # Baseline: the share of each outcome among earlier setups only, starting even.
    counts = np.ones(3)
    base = []
    for o in outcomes:
        base.append(counts / counts.sum())
        counts[o] += 1
    scores = {"Baseline: past frequencies": brier(np.array(base), outcomes)}
    for name in VERSIONS:
        scores[name] = brier(np.array([r[name] for r in rows]), outcomes)
    original = scores["Original: one bar at a time"]
    out = {"setups": len(rows), "actual": np.bincount(outcomes, minlength=3).tolist()}
    for name, values in scores.items():
        diff = values - original
        se = diff.std(ddof=1) / np.sqrt(len(diff)) if len(diff) > 1 else 0
        out[name] = {
            "brier": float(values.mean()),
            "vs_original": float(diff.mean()),
            "t": float(diff.mean() / se) if se > 0 else 0.0,
        }
    return out


if __name__ == "__main__":
    stocks = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    months = int(sys.argv[2]) if len(sys.argv) > 2 else 24
    from stockintel.db import get_engine

    tickers = universe(get_engine(), stocks)
    end = datetime.now(UTC)
    start = (pd.Timestamp(end).tz_convert(None) - pd.DateOffset(months=months)).replace(day=1)
    parts: dict[str, list] = {t: [] for t in tickers}
    source = provider()
    for month in pd.date_range(start, end.replace(tzinfo=None), freq="MS"):
        stop = min(month + pd.DateOffset(months=1), pd.Timestamp(end).tz_convert(None))
        frames, _ = fetch(
            source,
            tickers,
            month.tz_localize(UTC).to_pydatetime(),
            stop.tz_localize(UTC).to_pydatetime(),
            "5Min",
        )
        for ticker, frame in frames.items():
            parts[ticker].append(frame)
    days = {t: sessions(pd.concat(p, ignore_index=True)) for t, p in parts.items() if p}
    result = evaluate(days)
    print("TMEVAL", result)
