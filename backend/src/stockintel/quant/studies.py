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


def _month_end_closes(prices: pd.DataFrame) -> pd.DataFrame:
    """Each month's last close, indexed by the real last trading day of that month."""
    last_day = prices.index.to_series().groupby(prices.index.to_period("M")).max()
    return prices.loc[last_day.values]


def _monthly_to_daily(formation: pd.DataFrame, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Weights set at a month's last close, held through the next month's days."""
    return formation.reindex(index).ffill().fillna(0.0)


def momentum(
    prices: pd.DataFrame, mask: pd.DataFrame, top: float = 0.3, skip: int = 1, months: int = 12
) -> pd.DataFrame:
    """Long the 30% of stocks with the best return over months t-12 to t-2, short the worst
    30%, equal weight each side (Fama-French momentum breakpoints; their size split and value
    weights are left out: every stock here is large, and daily company sizes aren't stored).
    Decided at each month's last close, held through the next month."""
    closes = _month_end_closes(prices)
    past = closes.shift(skip) / closes.shift(months) - 1
    eligible = mask.reindex(closes.index, fill_value=False) & past.notna()
    rows = []
    for day in closes.index:
        score = past.loc[day][eligible.loc[day]]
        row = pd.Series(0.0, index=prices.columns)
        if len(score) >= 10:
            low, high = score.quantile(top), score.quantile(1 - top)
            winners, losers = score[score >= high].index, score[score <= low].index
            row[winners] = 1.0 / len(winners)
            row[losers] = -1.0 / len(losers)
        rows.append(row)
    return _monthly_to_daily(pd.DataFrame(rows, index=closes.index), prices.index)


def low_volatility(prices: pd.DataFrame, mask: pd.DataFrame, share: float = 0.1) -> pd.DataFrame:
    """Hold the calmest 10% of stocks, equal weight, ranked on the volatility of the past 3
    years (156 weeks) of weekly returns; rebalanced at each month's last close (Blitz & van
    Vliet, 2007). The rest of the money is fully invested in those stocks: no cash."""
    weekly = prices.resample("W-FRI").last().pct_change(fill_method=None)
    vol = weekly.rolling(156, min_periods=156).std()
    closes = _month_end_closes(prices)
    # The latest weekly reading known at each month-end close.
    known = vol.reindex(vol.index.union(closes.index)).ffill().reindex(closes.index)
    eligible = mask.reindex(closes.index, fill_value=False) & known.notna()
    rows = []
    for day in closes.index:
        score = known.loc[day][eligible.loc[day]]
        row = pd.Series(0.0, index=prices.columns)
        if len(score) >= 20:
            calm = score.nsmallest(max(1, round(len(score) * share))).index
            row[calm] = 1.0 / len(calm)
        rows.append(row)
    return _monthly_to_daily(pd.DataFrame(rows, index=closes.index), prices.index)
