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
    return {
        "close": latest,
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
