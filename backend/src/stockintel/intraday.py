"""Day trading rules after TJR's method, written as fixed rules so they can be tested.

Trades SPY and QQQ, which follow the S&P 500 and Nasdaq. A copy of the Day Trader repo's
tjr.py, kept separate so neither project depends on the other. Nothing here sends orders.

Source: the owner's notes on TJR's "Beginners Guide To Start Day Trading" video. The notes are an
AI summary, so where they were unclear a stated choice is made here and marked "Choice".

Bars are 1-minute bars with columns time (New York time), open, high, low, close, volume.
Every function looks only at bars that have closed, so nothing uses a price not yet known.
"""

from dataclasses import dataclass
from datetime import time

import pandas as pd

WINDOW = (time(9, 50), time(10, 30))  # Index trading window, New York time.
LAST_EXIT = time(15, 55)  # Day trades are closed before the market shuts.
MAX_TRADES = 2  # "1-2 high-quality trades per day."
MIN_REWARD = 1.0  # Reward at least equal to risk.
COST = 0.0002  # Choice: 0.02% each way for spread and slippage on SPY and QQQ.


@dataclass
class Gap:
    side: str  # "bullish" or "bearish"
    low: float
    high: float
    made: int  # Position of the third candle.


@dataclass
class Trade:
    ticker: str
    side: str  # "long" or "short"
    level: str
    confirmed_by: str
    entry_time: pd.Timestamp
    entry: float
    stop: float
    target: float
    exit_time: pd.Timestamp | None = None
    exit: float | None = None
    result: str | None = None  # "target", "stop" or "close"

    @property
    def r(self) -> float | None:
        """Result in units of risk, after costs."""
        if self.exit is None:
            return None
        risk = abs(self.entry - self.stop)
        move = self.exit - self.entry if self.side == "long" else self.entry - self.exit
        return (move - COST * (self.entry + self.exit)) / risk


def resample(frame: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Combine 1-minute bars into longer bars, labelled by when they start."""
    grouped = frame.set_index("time").resample(rule, label="left", closed="left")
    out = grouped.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna().reset_index()


def swings(frame: pd.DataFrame) -> list[tuple[int, str, float]]:
    """Swing points: an up candle then a down candle makes a high, and the reverse a low.

    Returns (known_from, kind, price). A swing is known only once the second candle has closed.
    """
    up = (frame["close"] > frame["open"]).to_numpy()
    down = (frame["close"] < frame["open"]).to_numpy()
    highs, lows = frame["high"].to_numpy(), frame["low"].to_numpy()
    found = []
    for i in range(len(frame) - 1):
        if up[i] and down[i + 1]:
            found.append((i + 1, "high", float(max(highs[i], highs[i + 1]))))
        if down[i] and up[i + 1]:
            found.append((i + 1, "low", float(min(lows[i], lows[i + 1]))))
    return found


def last_swing(points, kind: str, before: int) -> float | None:
    """The most recent swing of that kind known by position `before`."""
    known = [price for at, k, price in points if k == kind and at < before]
    return known[-1] if known else None


def break_of_structure(frame: pd.DataFrame, at: int, points=None) -> str | None:
    """A close beyond the last swing high (bullish) or low (bearish). Wicks don't count."""
    points = swings(frame) if points is None else points
    close = float(frame["close"].iloc[at])
    high, low = last_swing(points, "high", at), last_swing(points, "low", at)
    if high is not None and close > high:
        return "bullish"
    if low is not None and close < low:
        return "bearish"
    return None


def gaps(frame: pd.DataFrame, upto: int) -> list[Gap]:
    """Fair value gaps: the first candle's wick and the third candle's wick don't overlap."""
    highs, lows = frame["high"].to_numpy(), frame["low"].to_numpy()
    found = []
    for i in range(2, upto + 1):
        if lows[i] > highs[i - 2]:
            found.append(Gap("bullish", float(highs[i - 2]), float(lows[i]), i))
        elif highs[i] < lows[i - 2]:
            found.append(Gap("bearish", float(highs[i]), float(lows[i - 2]), i))
    return found


def inverse_gap(frame: pd.DataFrame, at: int, lookback: int = 30) -> str | None:
    """A gap that price closes through flips its meaning: a broken bullish gap is bearish."""
    close = float(frame["close"].iloc[at])
    previous = float(frame["close"].iloc[at - 1]) if at > 0 else close
    for gap in gaps(frame, at - 1):
        if gap.made < at - lookback:
            continue
        if gap.side == "bullish" and close < gap.low <= previous:
            return "bearish"
        if gap.side == "bearish" and close > gap.high >= previous:
            return "bullish"
    return None


def smt(first: pd.DataFrame, second: pd.DataFrame, at: int) -> str | None:
    """S&P and Nasdaq disagreeing at the latest swing: one makes a new extreme, one doesn't."""
    a, b = swings(first.iloc[: at + 1]), swings(second.iloc[: at + 1])

    def last_two(points, kind):
        prices = [p for k_at, k, p in points if k == kind and k_at <= at]
        return prices[-2:] if len(prices) >= 2 else None

    ah, bh = last_two(a, "high"), last_two(b, "high")
    if ah and bh and ((ah[1] > ah[0]) != (bh[1] > bh[0])):
        return "bearish"
    al, bl = last_two(a, "low"), last_two(b, "low")
    if al and bl and ((al[1] < al[0]) != (bl[1] < bl[0])):
        return "bullish"
    return None


def equilibrium(high: float, low: float) -> float:
    return (high + low) / 2


def key_levels(history: pd.DataFrame, day) -> dict[str, float]:
    """Levels known before the day's open: previous day, pre-market and 1-hour and 4-hour swings.

    Choice: SPY and QQQ don't trade in the Asian and London sessions, so the pre-market high
    and low stand in for them.
    """
    before = history[history["time"].dt.date < day]
    today = history[history["time"].dt.date == day]
    levels: dict[str, float] = {}
    if not before.empty:
        last = before[before["time"].dt.date == before["time"].dt.date.max()]
        regular = last[(last["time"].dt.time >= time(9, 30)) & (last["time"].dt.time < time(16))]
        if not regular.empty:
            levels["Previous day high"] = float(regular["high"].max())
            levels["Previous day low"] = float(regular["low"].min())
            levels["Previous day 50%"] = equilibrium(
                levels["Previous day high"], levels["Previous day low"]
            )
        for rule, name in (("1h", "1-hour"), ("4h", "4-hour")):
            bars = resample(before.tail(60 * 6 * 5), rule)
            points = swings(bars)
            high, low = last_swing(points, "high", len(bars)), last_swing(points, "low", len(bars))
            if high is not None:
                levels[f"{name} high"] = high
            if low is not None:
                levels[f"{name} low"] = low
    early = today[today["time"].dt.time < time(9, 30)]
    if not early.empty:
        levels["Pre-market high"] = float(early["high"].max())
        levels["Pre-market low"] = float(early["low"].min())
    return levels


def _exit(trade: Trade, after: pd.DataFrame, live: bool = False) -> Trade:
    for row in after.itertuples():
        if row.time.time() >= LAST_EXIT:
            trade.exit_time, trade.exit, trade.result = row.time, float(row.open), "close"
            return trade
        hit_stop = row.low <= trade.stop if trade.side == "long" else row.high >= trade.stop
        hit_target = row.high >= trade.target if trade.side == "long" else row.low <= trade.target
        if hit_stop:  # Choice: if both are touched in one minute, assume the stop came first.
            trade.exit_time, trade.exit, trade.result = row.time, trade.stop, "stop"
            return trade
        if hit_target:
            trade.exit_time, trade.exit, trade.result = row.time, trade.target, "target"
            return trade
    if not after.empty and not live:
        last = after.iloc[-1]
        trade.exit_time, trade.exit, trade.result = last["time"], float(last["close"]), "close"
    return trade


def scan_day(
    ticker: str,
    day_bars: pd.DataFrame,
    other: pd.DataFrame,
    levels: dict[str, float],
    live: bool = False,
    state: dict | None = None,
) -> list[Trade]:
    """Apply the steps to one day of 1-minute bars from the open. `other` is the paired index.

    With `live`, an unfinished trade stays open, and `state` is filled with the current step.
    """
    bars = day_bars[day_bars["time"].dt.time >= time(9, 30)].reset_index(drop=True)
    paired = other[other["time"].dt.time >= time(9, 30)].reset_index(drop=True)
    five = resample(bars, "5min")
    five_other = resample(paired, "5min")
    five_points = swings(five)
    one_points = swings(bars)
    trades: list[Trade] = []
    touched: tuple[str, str, int] | None = None  # (level name, wanted side, 5-min position)
    confirmed: tuple[str, int] | None = None
    for i in range(len(five)):
        start = five["time"].iloc[i]
        if start.time() < time(9, 30) or start.time() >= WINDOW[1] or len(trades) >= MAX_TRADES:
            continue
        if trades and trades[-1].exit_time is not None and start < trades[-1].exit_time:
            continue  # One trade at a time.
        if touched is None:
            # Step 3: price reaches a key level. A high level is looked at for a short.
            for name, price in levels.items():
                if five["high"].iloc[i] >= price > five["open"].iloc[i]:
                    touched = (name, "short", i)
                elif five["low"].iloc[i] <= price < five["open"].iloc[i]:
                    touched = (name, "long", i)
            continue
        if confirmed is None:
            want = "bearish" if touched[1] == "short" else "bullish"
            signals = {
                "5-minute break of structure": break_of_structure(five, i, five_points),
                "5-minute inverse fair value gap": inverse_gap(five, i),
                "S&P and Nasdaq disagree": smt(five, five_other, i)
                if len(five_other) > i
                else None,
            }
            reason = next((name for name, side in signals.items() if side == want), None)
            if reason:
                confirmed = (reason, i)
            continue
        # Step 4: on the 1-minute chart, after the 5-minute confirmation, wait for the entry.
        side = touched[1]
        want = "bearish" if side == "short" else "bullish"
        lo = bars.index[bars["time"] >= start][0]
        hi = bars.index[bars["time"] < start + pd.Timedelta(minutes=5)][-1]
        for j in range(lo, hi + 1):
            if bars["time"].iloc[j].time() < WINDOW[0]:
                continue
            signal = break_of_structure(bars, j, one_points) or inverse_gap(bars, j)
            if signal != want:
                continue
            since = bars.iloc[bars.index[bars["time"] >= five["time"].iloc[touched[2]]][0] : j + 1]
            entry = float(bars["close"].iloc[j])
            stop = float(since["high"].max() if side == "short" else since["low"].min())
            risk = abs(entry - stop)
            if risk <= 0:
                break
            targets = sorted(
                p for p in levels.values() if (p < entry if side == "short" else p > entry)
            )
            if side == "short":
                targets = targets[::-1]
            target = next((p for p in targets if abs(p - entry) >= MIN_REWARD * risk), None)
            if target is not None:
                trade = Trade(
                    ticker,
                    side,
                    touched[0],
                    confirmed[0],
                    bars["time"].iloc[j],
                    entry,
                    stop,
                    target,
                )
                trades.append(_exit(trade, bars.iloc[j + 1 :], live))
            touched = confirmed = None
            break
    if state is not None:
        state["touched"] = None if touched is None else {"level": touched[0], "side": touched[1]}
        state["confirmed"] = None if confirmed is None else confirmed[0]
    return trades


PAIR = {"SPY": "QQQ", "QQQ": "SPY"}
NY = "America/New_York"


def random_r(trade: Trade, bars: pd.DataFrame, rng) -> float | None:
    """The same entry time and distances, on a coin-flip side: what chance alone gives."""
    side = "long" if rng.random() < 0.5 else "short"
    risk, reward = abs(trade.entry - trade.stop), abs(trade.target - trade.entry)
    stop = trade.entry - risk if side == "long" else trade.entry + risk
    target = trade.entry + reward if side == "long" else trade.entry - reward
    copy = Trade(
        trade.ticker, side, "random", "random", trade.entry_time, trade.entry, stop, target
    )
    return _exit(copy, bars[bars["time"] > trade.entry_time]).r


def backtest(frames: dict[str, pd.DataFrame], seed: int = 0) -> list[dict]:
    """Run the rules over every day. Frames have a New York `time` column.

    Each day's levels come from earlier bars, and each step sees only closed bars."""
    import numpy as np

    rng = np.random.default_rng(seed)
    data = frames
    rows = []
    for symbol, other in PAIR.items():
        if symbol not in data or other not in data:
            continue
        mine, theirs = data[symbol], data[other]
        dates = mine["time"].dt.date
        days = sorted(set(dates))
        for n, day in enumerate(days[1:], 1):
            recent = mine[(dates >= days[max(0, n - 6)]) & (dates <= day)]
            today = mine[dates == day]
            paired = theirs[theirs["time"].dt.date == day]
            for trade in scan_day(symbol, today, paired, key_levels(recent, day)):
                if trade.r is None:
                    continue
                rows.append(
                    {
                        "symbol": symbol,
                        "entered": trade.entry_time,
                        "side": trade.side,
                        "level": trade.level,
                        "confirmed_by": trade.confirmed_by,
                        "r": trade.r,
                        "outcome": trade.result,
                        "random_r": random_r(trade, today, rng),
                    }
                )
    return rows
