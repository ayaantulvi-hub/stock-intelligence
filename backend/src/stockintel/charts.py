"""Chart engine: adjusted prices, indicators, levels and pattern rules. Pure calculations."""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from stockintel.market import sessions_between

TIMEFRAMES = {"daily", "weekly", "monthly"}
PIVOT_WINDOW = 5
LEVEL_LOOKBACK = 250
LEVEL_TOLERANCE = 0.015
MIN_TOUCHES = 2


def adjust(bars: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust for splits and dividends, as CRSP does.

    Needs oldest-first rows with open, high, low, close, volume, div_cash and split_factor.
    """
    frame = bars.copy()
    previous_close = frame["close"].shift(1)
    # Each event changes every earlier price, so factors accumulate from the newest bar back.
    split_step = 1 / frame["split_factor"]
    dividend_step = (1 - frame["div_cash"] / previous_close).fillna(1)
    split_factor = split_step.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1)
    price_factor = (split_step * dividend_step).iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1)
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column] * price_factor
    frame["volume"] = frame["volume"] / split_factor
    return frame[["market_date", "open", "high", "low", "close", "volume"]]


def resample(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """Build weekly or monthly candles from complete periods only."""
    if timeframe == "daily":
        return frame.reset_index(drop=True)
    rule = {"weekly": "W-FRI", "monthly": "ME"}[timeframe]
    indexed = frame.assign(market_date=pd.to_datetime(frame["market_date"])).set_index(
        "market_date"
    )
    grouped = indexed.groupby(pd.Grouper(freq=rule))
    candles = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna(subset=["close"])
    candles["market_date"] = [group.index[-1].date() for _, group in grouped if not group.empty]
    period_end = candles.index[-1].date() if len(candles) else None
    last = frame["market_date"].iloc[-1] if len(frame) else None
    if period_end and last and sessions_between(last + timedelta(days=1), period_end):
        candles = candles.iloc[:-1]
    return candles.reset_index(drop=True)[["market_date", "open", "high", "low", "close", "volume"]]


def sma(values: pd.Series, period: int) -> pd.Series:
    return values.rolling(period).mean()


def ema(values: pd.Series, period: int) -> pd.Series:
    """Exponential average seeded with the first simple average."""
    result = pd.Series(np.nan, index=values.index, dtype=float)
    data = values.to_numpy(dtype=float)
    if len(data) < period:
        return result
    weight = 2 / (period + 1)
    current = data[:period].mean()
    result.iloc[period - 1] = current
    for position in range(period, len(data)):
        current = data[position] * weight + current * (1 - weight)
        result.iloc[position] = current
    return result


def rsi(values: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's relative strength index, from 0 to 100."""
    result = pd.Series(np.nan, index=values.index, dtype=float)
    changes = values.diff().to_numpy(dtype=float)
    if len(changes) <= period:
        return result
    gains = np.clip(changes, 0, None)
    losses = np.clip(-changes, 0, None)
    average_gain = gains[1 : period + 1].mean()
    average_loss = losses[1 : period + 1].mean()

    def score() -> float:
        total = average_gain + average_loss
        return 100 * average_gain / total if total else 50.0

    result.iloc[period] = score()
    for position in range(period + 1, len(changes)):
        average_gain = (average_gain * (period - 1) + gains[position]) / period
        average_loss = (average_loss * (period - 1) + losses[position]) / period
        result.iloc[position] = score()
    return result


def macd(values: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    # Both averages start on the same bar, the convention TA-Lib also uses.
    fast_line = ema(values.iloc[slow - fast :], fast).reindex(values.index)
    slow_line = ema(values, slow)
    line = fast_line - slow_line
    signal_line = pd.Series(np.nan, index=values.index, dtype=float)
    valid = line.dropna()
    if len(valid) >= signal:
        signal_line.loc[valid.index] = ema(valid, signal)
    return pd.DataFrame({"macd": line, "signal": signal_line, "histogram": line - signal_line})


@dataclass(frozen=True)
class Level:
    kind: str
    price: float
    touches: int


def levels(frame: pd.DataFrame) -> list[Level]:
    """Support and resistance: prices where turning points cluster, nearest to the close."""
    recent = frame.tail(LEVEL_LOOKBACK).reset_index(drop=True)
    if len(recent) < PIVOT_WINDOW * 2 + 1:
        return []
    highs, lows = recent["high"], recent["low"]
    size = PIVOT_WINDOW * 2 + 1
    # The neighbour test stops a flat stretch counting as many separate turning points.
    pivot_highs = highs[
        (highs == highs.rolling(size, center=True).max()) & (highs > highs.shift(1))
    ]
    pivot_lows = lows[(lows == lows.rolling(size, center=True).min()) & (lows < lows.shift(1))]
    close = float(recent["close"].iloc[-1])
    clusters = _cluster(sorted([*pivot_highs, *pivot_lows]))
    above = [item for item in clusters if item[0] > close and item[1] >= MIN_TOUCHES]
    below = [item for item in clusters if item[0] < close and item[1] >= MIN_TOUCHES]
    result = []
    if above:
        price, touches = min(above)
        result.append(Level("resistance", price, touches))
    if below:
        price, touches = max(below)
        result.append(Level("support", price, touches))
    return result


def _cluster(prices: list[float]) -> list[tuple[float, int]]:
    groups: list[list[float]] = []
    for price in prices:
        if groups and price <= groups[-1][0] * (1 + LEVEL_TOLERANCE):
            groups[-1].append(price)
        else:
            groups.append([price])
    return [(sum(group) / len(group), len(group)) for group in groups]


def summary(frame: pd.DataFrame, found: list[Level]) -> dict | None:
    """Plain facts about the newest candle. Descriptions only, never predictions."""
    if frame.empty:
        return None
    close = frame["close"]
    latest = float(close.iloc[-1])
    previous = float(close.iloc[-2]) if len(close) > 1 else None
    average_50 = sma(close, 50).iloc[-1]
    average_200 = sma(close, 200).iloc[-1]
    strength = rsi(close).iloc[-1]

    def above(value: float) -> bool | None:
        return None if np.isnan(value) else bool(latest > value)

    def percent_to(kind: str) -> float | None:
        level = next((item.price for item in found if item.kind == kind), None)
        return None if level is None else (level / latest - 1) * 100

    if np.isnan(strength):
        rsi_state = None
    elif strength >= 70:
        rsi_state = "Overbought"
    elif strength <= 30:
        rsi_state = "Oversold"
    else:
        rsi_state = "Middle range"

    def level_price(kind: str) -> float | None:
        return next((item.price for item in found if item.kind == kind), None)

    return {
        "close": latest,
        "average_50": None if np.isnan(average_50) else float(average_50),
        "average_200": None if np.isnan(average_200) else float(average_200),
        "resistance": level_price("resistance"),
        "support": level_price("support"),
        "change_percent": (latest / previous - 1) * 100 if previous else None,
        "above_50": above(average_50),
        "above_200": above(average_200),
        "rsi": None if np.isnan(strength) else float(strength),
        "rsi_state": rsi_state,
        "percent_to_resistance": percent_to("resistance"),
        "percent_to_support": percent_to("support"),
    }


@dataclass(frozen=True)
class Pattern:
    name: str
    direction: str
    state: str  # "confirmed" or "forming"
    market_date: date
    cancellation_level: float
    detail: str


PATTERNS = (
    ("Double top", "bearish"),
    ("Double bottom", "bullish"),
    ("Head and shoulders", "bearish"),
    ("Inverse head and shoulders", "bullish"),
    ("Ascending triangle", "bullish"),
    ("Descending triangle", "bearish"),
)
SAME_LEVEL = 0.015
SHOULDER_LEVEL = 0.03
MIN_DEPTH = 0.03
MIN_HEAD = 0.02
MIN_GAP, MAX_GAP = 10, 60


def _pivots(values: np.ndarray, sign: int) -> list[int]:
    """Turning points, as positions. sign 1 finds peaks and -1 finds troughs."""
    found = []
    data = values * sign
    for i in range(PIVOT_WINDOW, len(data) - PIVOT_WINDOW):
        around = data[i - PIVOT_WINDOW : i + PIVOT_WINDOW + 1]
        if data[i] == around.max() and data[i] > data[i - 1]:
            found.append(i)
    return found


def _near(a: float, b: float, tolerance: float) -> bool:
    return abs(a / b - 1) <= tolerance


def chart_patterns(frame: pd.DataFrame) -> list[tuple[str, str, int, float]]:
    """Find completed shapes as (name, direction, position, cancellation level).

    A shape completes when the close crosses its key line. A turning point only counts
    once PIVOT_WINDOW later candles have closed, so nothing here uses future prices.
    """
    highs = frame["high"].to_numpy(dtype=float)
    lows = frame["low"].to_numpy(dtype=float)
    close = frame["close"].to_numpy(dtype=float)
    peaks, troughs = _pivots(highs, 1), _pivots(lows, -1)
    found: list[tuple[str, str, int, float]] = []
    seen: set[tuple[str, float]] = set()

    def add(name, direction, position, level, key):
        if (name, key) not in seen:
            seen.add((name, key))
            found.append((name, direction, position, float(level)))

    def crossed_down(line: float, moment: int) -> bool:
        return bool(close[moment - 1] >= line > close[moment])

    def crossed_up(line: float, moment: int) -> bool:
        return bool(close[moment - 1] <= line < close[moment])

    p, t = 0, 0
    known_peaks: list[int] = []
    known_troughs: list[int] = []
    for now in range(1, len(close)):
        while p < len(peaks) and peaks[p] + PIVOT_WINDOW <= now:
            known_peaks.append(peaks[p])
            p += 1
        while t < len(troughs) and troughs[t] + PIVOT_WINDOW <= now:
            known_troughs.append(troughs[t])
            t += 1
        if len(known_peaks) >= 2:
            a, b = known_peaks[-2], known_peaks[-1]
            between = [i for i in known_troughs if a < i < b]
            if MIN_GAP <= b - a <= MAX_GAP and between and now - b <= MAX_GAP:
                neck = lows[between].min()
                top = max(highs[a], highs[b])
                if (
                    _near(highs[a], highs[b], SAME_LEVEL)
                    and neck <= top * (1 - MIN_DEPTH)
                    and crossed_down(neck, now)
                ):
                    add("Double top", "bearish", now, top, b)
        if len(known_troughs) >= 2:
            a, b = known_troughs[-2], known_troughs[-1]
            between = [i for i in known_peaks if a < i < b]
            if MIN_GAP <= b - a <= MAX_GAP and between and now - b <= MAX_GAP:
                neck = highs[between].max()
                bottom = min(lows[a], lows[b])
                if (
                    _near(lows[a], lows[b], SAME_LEVEL)
                    and neck >= bottom * (1 + MIN_DEPTH)
                    and crossed_up(neck, now)
                ):
                    add("Double bottom", "bullish", now, bottom, b)
        if len(known_peaks) >= 3 and len(known_troughs) >= 2:
            left, head, right = known_peaks[-3:]
            dips = [i for i in known_troughs if left < i < right]
            if dips and now - right <= MAX_GAP and right - left <= MAX_GAP * 2:
                neck = lows[dips].min()
                if (
                    highs[head] >= max(highs[left], highs[right]) * (1 + MIN_HEAD)
                    and _near(highs[left], highs[right], SHOULDER_LEVEL)
                    and crossed_down(neck, now)
                ):
                    add("Head and shoulders", "bearish", now, highs[right], right)
        if len(known_troughs) >= 3 and len(known_peaks) >= 2:
            left, head, right = known_troughs[-3:]
            rises = [i for i in known_peaks if left < i < right]
            if rises and now - right <= MAX_GAP and right - left <= MAX_GAP * 2:
                neck = highs[rises].max()
                if (
                    lows[head] <= min(lows[left], lows[right]) * (1 - MIN_HEAD)
                    and _near(lows[left], lows[right], SHOULDER_LEVEL)
                    and crossed_up(neck, now)
                ):
                    add("Inverse head and shoulders", "bullish", now, lows[right], right)
        if len(known_peaks) >= 2 and len(known_troughs) >= 2:
            a, b = known_peaks[-2], known_peaks[-1]
            c, d = known_troughs[-2], known_troughs[-1]
            recent = now - min(a, c) <= MAX_GAP * 2
            flat_top = _near(highs[a], highs[b], SAME_LEVEL) and lows[d] > lows[c] * 1.01
            flat_base = _near(lows[c], lows[d], SAME_LEVEL) and highs[b] < highs[a] * 0.99
            if recent and flat_top and crossed_up(max(highs[a], highs[b]), now):
                add("Ascending triangle", "bullish", now, lows[d], b)
            if recent and flat_base and crossed_down(min(lows[c], lows[d]), now):
                add("Descending triangle", "bearish", now, highs[b], d)
    return found


def pattern_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Where each rule was confirmed on every candle, as one true/false column per rule.

    The same rules as detect_patterns, without support and resistance, written for whole
    price histories. A test holds the two in step.
    """
    close, open_ = frame["close"], frame["open"]
    short, long = sma(close, 50), sma(close, 200)
    lines = macd(close)["histogram"]
    strength = rsi(close)
    previous_close, previous_open = close.shift(1), open_.shift(1)
    up = (close > open_) & (previous_close < previous_open)
    down = (close < open_) & (previous_close > previous_open)
    flags = pd.DataFrame(
        {
            ("Golden cross", "bullish"): (short.shift(1) <= long.shift(1)) & (short > long),
            ("Death cross", "bearish"): (short.shift(1) >= long.shift(1)) & (short < long),
            ("MACD cross", "bullish"): (lines.shift(1) <= 0) & (lines > 0),
            ("MACD cross", "bearish"): (lines.shift(1) >= 0) & (lines < 0),
            ("RSI recovery", "bullish"): (strength.shift(1) < 30) & (strength >= 30),
            ("RSI rollover", "bearish"): (strength.shift(1) > 70) & (strength <= 70),
            ("Bullish engulfing", "bullish"): up
            & (open_ <= previous_close)
            & (close >= previous_open),
            ("Bearish engulfing", "bearish"): down
            & (open_ >= previous_close)
            & (close <= previous_open),
        }
    )
    for key in PATTERNS:
        flags[key] = False
    for name, direction, position, _ in chart_patterns(frame):
        flags.iloc[position, flags.columns.get_loc((name, direction))] = True
    return flags


def pattern_score(frame: pd.DataFrame, days: int = 10) -> pd.Series:
    """Plus 1 after a bullish shape and minus 1 after a bearish one, for `days` candles."""
    score = pd.Series(0.0, index=frame.index)
    for _, direction, position, _ in chart_patterns(frame):
        value = 1.0 if direction == "bullish" else -1.0
        score.iloc[position : position + days] = value
    return score


def detect_patterns(frame: pd.DataFrame) -> list[Pattern]:
    """Apply fixed rules to the newest candle. Needs oldest-first adjusted candles."""
    if len(frame) < 2:
        return []
    close = frame["close"]
    latest = frame.iloc[-1]
    previous = frame.iloc[-2]
    day = latest["market_date"]
    recent_low = float(frame["low"].tail(5).min())
    recent_high = float(frame["high"].tail(5).max())
    found: list[Pattern] = []

    def add(name, direction, state, level, detail):
        found.append(Pattern(name, direction, state, day, float(level), detail))

    short, long = sma(close, 50), sma(close, 200)
    if len(frame) >= 201 and not np.isnan(long.iloc[-2]):
        crossed_up = short.iloc[-2] <= long.iloc[-2] and short.iloc[-1] > long.iloc[-1]
        crossed_down = short.iloc[-2] >= long.iloc[-2] and short.iloc[-1] < long.iloc[-1]
        gap = short.iloc[-1] / long.iloc[-1] - 1
        previous_gap = short.iloc[-2] / long.iloc[-2] - 1
        closing = abs(gap) < abs(previous_gap)
        if crossed_up:
            add(
                "Golden cross",
                "bullish",
                "confirmed",
                long.iloc[-1],
                "50 average crossed above 200",
            )
        elif crossed_down:
            add(
                "Death cross", "bearish", "confirmed", long.iloc[-1], "50 average crossed below 200"
            )
        elif abs(gap) < 0.01 and closing:
            if previous_gap < 0:
                add("Golden cross", "bullish", "forming", long.iloc[-1], "50 average nearing 200")
            else:
                add("Death cross", "bearish", "forming", long.iloc[-1], "50 average nearing 200")

    lines = macd(close)
    if not lines["signal"].iloc[-2:].isna().any():
        before = lines["histogram"].iloc[-2]
        now = lines["histogram"].iloc[-1]
        if before <= 0 < now:
            add("MACD cross", "bullish", "confirmed", recent_low, "MACD crossed above its signal")
        elif before >= 0 > now:
            add("MACD cross", "bearish", "confirmed", recent_high, "MACD crossed below its signal")

    strength = rsi(close)
    if not strength.iloc[-2:].isna().any():
        if strength.iloc[-2] < 30 <= strength.iloc[-1]:
            add("RSI recovery", "bullish", "confirmed", recent_low, "RSI rose back above 30")
        elif strength.iloc[-2] > 70 >= strength.iloc[-1]:
            add("RSI rollover", "bearish", "confirmed", recent_high, "RSI fell back below 70")

    body_up = latest["close"] > latest["open"]
    prior_down = previous["close"] < previous["open"]
    if (
        body_up
        and prior_down
        and latest["open"] <= previous["close"]
        and latest["close"] >= previous["open"]
    ):
        add(
            "Bullish engulfing",
            "bullish",
            "confirmed",
            latest["low"],
            "Up candle covers last down candle",
        )
    elif (
        latest["close"] < latest["open"]
        and previous["close"] > previous["open"]
        and latest["open"] >= previous["close"]
        and latest["close"] <= previous["open"]
    ):
        add(
            "Bearish engulfing",
            "bearish",
            "confirmed",
            latest["high"],
            "Down candle covers last up candle",
        )

    for name, direction, position, level in chart_patterns(frame):
        if position == len(frame) - 1:
            add(name, direction, "confirmed", level, f"{name} completed on this candle")

    for level in levels(frame.iloc[:-1]):
        if level.kind == "resistance":
            if previous["close"] <= level.price < latest["close"]:
                add("Breakout", "bullish", "confirmed", level.price, "Closed above resistance")
            elif 0 < level.price / latest["close"] - 1 < 0.01:
                add("Breakout", "bullish", "forming", level.price, "Within 1% of resistance")
        elif previous["close"] >= level.price > latest["close"]:
            add("Breakdown", "bearish", "confirmed", level.price, "Closed below support")
        elif 0 < 1 - level.price / latest["close"] < 0.01:
            add("Breakdown", "bearish", "forming", level.price, "Within 1% of support")
    return found
