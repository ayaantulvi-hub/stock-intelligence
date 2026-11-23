"""Volatility-managed portfolios.

The managed portfolio holds w_t times the market, where w_t falls when recent risk is high:
- variance managed: w = c / (last month's realised variance), as in Moreira & Muir (2017);
- volatility targeting: w = target / (last month's realised volatility);
- conditional (Bongaerts, Kang & van Dijk, 2020): scale only when last month's volatility is in
  the top or bottom fifth of all months so far; otherwise hold the market unchanged;
- daily EWMA (Harvey et al., 2018): volatility from daily returns with a 20-day half-life,
  rebalanced every day. Their scale is set on the full sample; here it is the average of past
  volatility only, so nothing uses later data (the real-time point of Cederburg et al., 2020).
Weights are set at each month's first close from the previous month's daily returns only, and
capped at MAX_LEVERAGE. The scale c (and the target) come from an expanding average of past
risk, so nothing uses future data. Everything is in excess returns over the Fed funds rate:
money not invested earns that rate, and borrowed money costs it.
"""

import numpy as np
import pandas as pd

from stockintel.quant.engine import COST_BPS

WINDOW = 21  # Trading days in the "last month".
MAX_LEVERAGE = 2.0  # An assumption: a typical limit for a margin account.
HALF_LIFE = 20  # Days, Harvey et al.'s default estimate.
MIN_HISTORY_MONTHS = 60  # Conditional: months of history before it trades. The paper asks for
# 10 years; 16 years of data would leave too little to test, so 5 years is used, fixed in advance.
QUINTILE = 0.2


def realised(excess: pd.Series) -> pd.DataFrame:
    """Each day: variance and volatility of the past WINDOW days' returns (annualised)."""
    var = (excess**2).rolling(WINDOW, min_periods=WINDOW).mean() * 252
    return pd.DataFrame({"var": var, "vol": np.sqrt(var)})


def weights(excess: pd.Series, kind: str) -> pd.Series:
    """Exposure to the market for each day, decided at the first close of each month."""
    risk = realised(excess)
    months = pd.Series(excess.index.to_period("M"), index=excess.index)
    month_start = months.ne(months.shift(1))
    measure = risk["var"] if kind == "variance" else risk["vol"]
    # The scale: average past risk up to that day, so average exposure is near 1.
    scale = measure.expanding(min_periods=WINDOW * 12).mean()
    raw = (scale / measure).clip(upper=MAX_LEVERAGE)
    decided = raw.where(month_start).ffill()
    return decided


def conditional_held(excess: pd.Series) -> pd.Series:
    """Exposure held on each day of month m, set at the last close of month m-1 from:
    - last month's volatility, without its final day, so it is known before the close;
    - the target: volatility of every daily return before month m;
    - the fifths: last-month volatilities of every month up to m-1."""
    months = excess.index.to_period("M")
    groups = {m: g for m, g in excess.groupby(months)}
    order = sorted(groups)
    month_vol = {
        m: float(groups[m].iloc[:-1].std(ddof=1) * np.sqrt(252))
        for m in order
        if len(groups[m]) > 2
    }
    held = pd.Series(np.nan, index=excess.index)
    for i, m in enumerate(order[1:], start=1):
        past = [month_vol[x] for x in order[:i] if x in month_vol]
        if len(past) < MIN_HISTORY_MONTHS or order[i - 1] not in month_vol:
            continue
        before = excess[excess.index < groups[m].index[0]]
        target = float(before.std(ddof=1) * np.sqrt(252))
        last = month_vol[order[i - 1]]
        low, high = np.quantile(past, [QUINTILE, 1 - QUINTILE])
        w = min(target / last, MAX_LEVERAGE) if (last >= high or last <= low) else 1.0
        held[groups[m].index] = w
    return held


def ewma_held(excess: pd.Series) -> pd.Series:
    """Exposure held each day: decided at the previous close from an exponentially weighted
    volatility (20-day half-life, around zero) and the average of all earlier such volatility."""
    vol = np.sqrt((excess**2).ewm(halflife=HALF_LIFE, adjust=False, min_periods=60).mean() * 252)
    target = vol.expanding(min_periods=252).mean()
    return (target / vol).clip(upper=MAX_LEVERAGE).shift(1)


def managed(
    excess: pd.Series, kind: str, cost_bps: float = COST_BPS
) -> tuple[pd.Series, pd.Series]:
    """(managed excess returns after costs, exposure held each day). Exposure decided at a
    close is held from the next day; changing it costs cost_bps per unit traded."""
    if kind == "conditional":
        held = conditional_held(excess)
    elif kind == "ewma":
        held = ewma_held(excess)
    else:
        held = weights(excess, kind).shift(1)
    cost = held.diff().abs().fillna(0) * cost_bps / 10_000
    out = held * excess - cost
    return out[held.notna()], held[held.notna()]
