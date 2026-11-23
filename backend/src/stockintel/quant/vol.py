"""Volatility-managed portfolios (Moreira & Muir, 2017).

The managed portfolio holds w_t times the market, where w_t falls when recent risk is high:
- variance managed: w = c / (last month's realised variance), as in Moreira & Muir;
- volatility targeting: w = target / (last month's realised volatility).
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


def managed(
    excess: pd.Series, kind: str, cost_bps: float = COST_BPS
) -> tuple[pd.Series, pd.Series]:
    """(managed excess returns after costs, exposure held each day). Exposure decided at a
    close is held from the next day; changing it costs cost_bps per unit traded."""
    w = weights(excess, kind)
    held = w.shift(1)
    cost = w.diff().abs().shift(1).fillna(0) * cost_bps / 10_000
    out = held * excess - cost
    return out[held.notna()], held[held.notna()]
