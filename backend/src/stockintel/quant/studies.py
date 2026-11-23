"""Strategy rules for the quant lab. Each returns target weights decided at each day's close,
using only data up to that close. Parameters are the classic published or textbook values,
fixed before testing."""

import numpy as np
import pandas as pd

from stockintel.quant.engine import COST_BPS


def equal_weight(mask: pd.DataFrame) -> pd.DataFrame:
    """Hold every tradeable stock equally: the baseline."""
    held = mask.astype(float)
    return held.div(held.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def ma_crossover(
    prices: pd.DataFrame, mask: pd.DataFrame, fast: int = 50, slow: int = 200
) -> pd.DataFrame:
    """Own a stock while its 50-day average is above its 200-day average, equally weighted
    among the stocks that qualify; the rest of the money stays in cash. A common textbook
    trend rule; its values are not tuned here."""
    fast_avg = prices.rolling(fast, min_periods=fast).mean()
    slow_avg = prices.rolling(slow, min_periods=slow).mean()
    on = (fast_avg > slow_avg) & mask
    count = mask.sum(axis=1).replace(0, np.nan)
    return on.astype(float).div(count, axis=0).fillna(0.0)


def trend_on(level: pd.Series, fast: int = 50, slow: int = 200) -> pd.Series:
    """1.0 at a close when an index's 50-day average is above its 200-day average, else 0.0;
    NaN until 200 days exist, so the warm-up never counts as a decision."""
    fast_avg = level.rolling(fast, min_periods=fast).mean()
    slow_avg = level.rolling(slow, min_periods=slow).mean()
    return (fast_avg > slow_avg).astype(float).where(slow_avg.notna())


def trend_returns(on: pd.Series, excess: pd.Series, cost_bps: float = COST_BPS) -> pd.Series:
    """Excess return of holding the index only while trending up, decided at each close and
    held from the next day. Out of the market it earns the risk-free rate, so its excess
    return is 0. Each switch in or out costs cost_bps."""
    held = on.shift(1)
    cost = held.diff().abs().fillna(0) * cost_bps / 10_000
    out = held * excess - cost
    return out[held.notna() & excess.notna()]
