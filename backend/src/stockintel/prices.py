"""Price adjustment and point-in-time size filters shared by the quant studies."""

from collections import defaultdict

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

# A company counts as large in a year if it ranked in about the top 1,000 by public float.
SIZE_LIMIT = 1000


def adjust(bars: pd.DataFrame) -> pd.DataFrame:
    """Back-adjust for splits and dividends, as CRSP does.

    Needs oldest-first rows with open, high, low, close, volume, div_cash and split_factor.
    """
    frame = bars.copy()
    # A split and a payout can share a day. The payout is in post-split dollars, so the
    # previous close must be too, or the factor can turn negative.
    previous_close = (frame["close"].shift(1) / frame["split_factor"]).where(
        frame["split_factor"] > 0
    )
    # Each event changes every earlier price, so factors accumulate from the newest bar back.
    split_step = 1 / frame["split_factor"]
    dividend_step = (1 - frame["div_cash"] / previous_close).fillna(1)
    split_factor = split_step.iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1)
    price_factor = (split_step * dividend_step).iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1)
    for column in ("open", "high", "low", "close"):
        frame[column] = frame[column] * price_factor
    frame["volume"] = frame["volume"] / split_factor
    return frame[["market_date", "open", "high", "low", "close", "volume"]]


def eligibility(engine: Engine) -> dict[int, set[int]]:
    """For each company, the years it ranked among the largest, as known at the time."""
    query = "SELECT year, cik FROM historic_float WHERE size_rank <= :limit"
    table: dict[int, set[int]] = defaultdict(set)
    with engine.connect() as conn:
        for year, cik in conn.execute(text(query), {"limit": SIZE_LIMIT}):
            table[cik].add(year)
    return table


def eligible_days(dates: pd.Series, years: set[int]) -> np.ndarray:
    """A mid-year size is reported in filings by about the next March, so use it from April."""
    days = pd.to_datetime(dates)
    known = np.where(days.dt.month >= 4, days.dt.year - 1, days.dt.year - 2)
    return np.isin(known, sorted(years))
