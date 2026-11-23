"""Strategy rules for the quant lab. Each returns target weights decided at each day's close,
using only data up to that close. Parameters are the classic published or textbook values,
fixed before testing."""

import numpy as np
import pandas as pd


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
