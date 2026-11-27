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


def factor_momentum(
    factors: pd.DataFrame, months: int = 12, cost_bps: float = COST_BPS
) -> tuple[pd.Series, pd.DataFrame]:
    """Time-series factor momentum (Ehsani & Linnainmaa, 2022): at each month's last close, go
    long every factor whose return over the past 12 months was positive and short every factor
    whose return was negative, equal weight across all of them, held through the next month.
    A factor joins once it has 12 full months of history. Returns (daily return after costs,
    position held each day). Flipping a factor's side costs cost_bps per unit traded."""
    growth = (1 + factors.fillna(0)).cumprod().where(factors.notna())
    month_end = factors.index.to_series().groupby(factors.index.to_period("M")).max()
    ends = pd.DatetimeIndex(month_end.values)
    rows = []
    for i, end in enumerate(ends):
        row = pd.Series(np.nan, index=factors.columns)
        if i >= months:
            # Growth over the 12 months up to this close: NaN unless the factor already had
            # data at the window's start, so a factor joins only with a full year behind it.
            past = growth.loc[end] / growth.loc[ends[i - months]] - 1
            row[past > 0] = 1.0
            row[past < 0] = -1.0
        rows.append(row)
    signs = pd.DataFrame(rows, index=ends)
    held = signs.reindex(factors.index).ffill().shift(1)
    active = held.notna().sum(axis=1)
    weights = held.div(active.where(active > 0), axis=0)
    gross = (weights * factors).sum(axis=1, min_count=1)
    cost = weights.fillna(0).diff().abs().sum(axis=1) * cost_bps / 10_000
    out = (gross - cost)[active > 0]
    return out, held.loc[out.index]


def mean_reversion(
    prices: pd.DataFrame, mask: pd.DataFrame, window: int = 20, entry: float = 2.0
) -> pd.DataFrame:
    """Bollinger-band mean reversion. z = (P - MA20) / sd20 of closes. Long a stock when z
    falls below -2, short when it rises above +2, and close each position when z crosses back
    through 0. Equal weight across open positions, gross exposure 1. Decided at each close."""
    ma = prices.rolling(window, min_periods=window).mean()
    sd = prices.rolling(window, min_periods=window).std()
    z = ((prices - ma) / sd).where(mask.reindex_like(prices).fillna(False).astype(bool))
    values = z.to_numpy()
    state = np.zeros(values.shape[1])
    out = np.zeros_like(values)
    for t in range(values.shape[0]):
        zt = values[t]
        known = np.isfinite(zt)
        state[~known] = 0.0  # No reading (or not eligible): no position.
        state[known & (state == 1) & (zt >= 0)] = 0.0
        state[known & (state == -1) & (zt <= 0)] = 0.0
        state[known & (state == 0) & (zt < -entry)] = 1.0
        state[known & (state == 0) & (zt > entry)] = -1.0
        active = np.abs(state).sum()
        out[t] = state / active if active else 0.0
    return pd.DataFrame(out, index=prices.index, columns=prices.columns)


def _channel(values: np.ndarray, entry: int, exit_: int) -> np.ndarray:
    """1 while in a Donchian breakout: in when the close beats the highest close of the prior
    `entry` days, out when it falls below the lowest close of the prior `exit_` days."""
    frame = pd.DataFrame(values)
    high = frame.rolling(entry, min_periods=entry).max().shift(1).to_numpy()
    low = frame.rolling(exit_, min_periods=exit_).min().shift(1).to_numpy()
    state = np.zeros(values.shape[1])
    out = np.zeros_like(values, dtype=float)
    for t in range(values.shape[0]):
        p = values[t]
        known = np.isfinite(p) & np.isfinite(high[t]) & np.isfinite(low[t])
        state[~np.isfinite(p)] = 0.0
        state[known & (state == 1) & (p < low[t])] = 0.0
        state[known & (state == 0) & (p > high[t])] = 1.0
        out[t] = state
    return out


def breakout(
    prices: pd.DataFrame, mask: pd.DataFrame, entry: int = 55, exit_: int = 20
) -> pd.DataFrame:
    """Donchian channel breakout (the Turtle rules' System 2: 55-day entry, 20-day exit), on
    closes, long only. Equal weight across stocks in a breakout; the rest is cash."""
    on = pd.DataFrame(
        _channel(prices.to_numpy(), entry, exit_), index=prices.index, columns=prices.columns
    )
    on = on.where(mask.reindex_like(prices).fillna(False).astype(bool), 0.0)
    count = on.sum(axis=1)
    return on.div(count.where(count > 0), axis=0).fillna(0.0)


def breakout_on(level: pd.Series, entry: int = 55, exit_: int = 20) -> pd.Series:
    """The same breakout rule on one index level: 1.0 in, 0.0 out, NaN until 55 days exist."""
    on = _channel(level.to_numpy().reshape(-1, 1), entry, exit_)[:, 0]
    return pd.Series(on, index=level.index).where(np.arange(len(level)) >= entry)
