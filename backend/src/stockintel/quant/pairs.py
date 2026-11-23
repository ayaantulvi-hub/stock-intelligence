"""Pairs trading, two ways, on the same formation and trading windows.

Distance method (Gatev, Goetzmann & Rouwenhorst, 2006), as written in the paper:
- Form pairs on 12 months: each stock's total-return index is scaled to 1 at the start, and
  pairs with the smallest sum of squared differences are chosen (top 20). Stocks with any
  missing day in the window are dropped.
- Trade the next 6 months, with prices rescaled to 1 at the last formation close (an
  implementation choice: each pair starts level): open when the gap between the two scaled prices is more than 2
  formation-period standard deviations (long the lower, short the higher, equal money); close
  when the prices cross; close anything still open on the last day.
- "Wait one day": orders are filled a day after the signal, to avoid bid-ask bounce.
- Returns are on committed capital: divided by all 20 pairs, traded or not.

Cointegration method (Engle & Granger, 1987):
- On the same 12 months, regress log price A on log price B; the leftover (the spread) must
  pass an Engle-Granger test at 5%. The 20 pairs with the lowest p-values are kept.
- Trade the spread's z-score (its formation mean and spread fixed): open beyond +/-2, close
  when it crosses 0, same one-day wait, money split by the hedge ratio.

To keep the search small and the pairs economically related, both methods only pair stocks in
the same industry (first two digits of the SEC industry code), as Do & Faff (2010) found
helps. Differences from the paper are stated: daily rebalanced weights instead of
buy-and-hold legs, and today's stock list (survivorship bias).
"""

from dataclasses import dataclass
from itertools import combinations

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

FORMATION = 252
TRADING = 126
TOP = 20
OPEN_AT = 2.0
COINT_P = 0.05


@dataclass
class Pair:
    a: str
    b: str
    score: float  # Sum of squared differences, or the cointegration p-value.
    hedge: float = 1.0  # Units of B per unit of A (cointegration only).
    mean: float = 0.0
    sd: float = 1.0


def _complete(window: pd.DataFrame, tradeable: pd.Series) -> list[str]:
    """Stocks tradeable at the end of formation with a price every day of the window."""
    full = window.notna().all()
    return [t for t in window.columns if full[t] and bool(tradeable.get(t, False))]


def distance_pairs(window: pd.DataFrame, groups: dict[str, str], top: int = TOP) -> list[Pair]:
    scaled = window / window.iloc[0]
    found = []
    for a, b in combinations(scaled.columns, 2):
        if groups.get(a) is None or groups.get(a) != groups.get(b):
            continue
        gap = scaled[a] - scaled[b]
        found.append(Pair(a, b, float((gap**2).sum()), mean=0.0, sd=float(gap.std(ddof=0))))
    return sorted(found, key=lambda p: p.score)[:top]


def coint_pairs(window: pd.DataFrame, groups: dict[str, str], top: int = TOP) -> list[Pair]:
    logs = np.log(window)
    found = []
    for a, b in combinations(logs.columns, 2):
        if groups.get(a) is None or groups.get(a) != groups.get(b):
            continue
        _, p, _ = coint(logs[a], logs[b], maxlag=1, autolag=None)
        if p >= COINT_P:
            continue
        x = np.column_stack([np.ones(len(logs)), logs[b].to_numpy()])
        intercept, hedge = np.linalg.lstsq(x, logs[a].to_numpy(), rcond=None)[0]
        spread = logs[a] - hedge * logs[b] - intercept
        if hedge <= 0:
            continue  # A negative hedge would mean owning or shorting both: not a pair trade.
        found.append(
            Pair(
                a,
                b,
                float(p),
                hedge=float(hedge),
                mean=float(intercept),
                sd=float(spread.std(ddof=0)),
            )
        )
    return sorted(found, key=lambda p: p.score)[:top]


def _gap(pair: Pair, method: str, prices: pd.DataFrame, start_prices: pd.Series) -> pd.Series:
    """The pair's signal through the trading window, in formation standard deviations."""
    if method == "distance":
        gap = prices[pair.a] / start_prices[pair.a] - prices[pair.b] / start_prices[pair.b]
    else:
        gap = np.log(prices[pair.a]) - pair.hedge * np.log(prices[pair.b]) - pair.mean
    return gap / pair.sd if pair.sd > 0 else gap * np.nan


def positions(gap: pd.Series) -> pd.Series:
    """+1 = long A short B, -1 = short A long B, 0 = out. Open beyond +/-2, close at the cross,
    close on the last day. A missing price closes the position (the paper's delisting rule)."""
    state, out = 0, []
    values = gap.to_numpy()
    for i, z in enumerate(values):
        if np.isnan(z):
            state = 0
        elif state == 0:
            state = -1 if z > OPEN_AT else (1 if z < -OPEN_AT else 0)
        elif (state == 1 and z >= 0) or (state == -1 and z <= 0):
            state = 0
        if i == len(values) - 1:
            state = 0
        out.append(state)
    return pd.Series(out, index=gap.index, dtype=float)


def period_weights(
    method: str, prices: pd.DataFrame, mask: pd.DataFrame, groups: dict[str, str], form_start: int
) -> tuple[pd.DataFrame, list[Pair]]:
    """Weights for one trading window, decided only from data up to each day."""
    form = prices.iloc[form_start : form_start + FORMATION]
    trade = prices.iloc[form_start + FORMATION : form_start + FORMATION + TRADING]
    names = _complete(form, mask.iloc[form_start + FORMATION - 1])
    form = form[names]
    chosen = (distance_pairs if method == "distance" else coint_pairs)(form, groups)
    weights = pd.DataFrame(0.0, index=trade.index, columns=prices.columns)
    if trade.empty:
        return weights, chosen
    # Implementation choice: in the trading window, prices are rescaled to 1 at the last
    # formation close, so every pair starts level and must newly diverge to open.
    start_prices = form.iloc[-1]
    for pair in chosen:
        state = positions(_gap(pair, method, trade, start_prices))
        if method == "distance":
            share_a, share_b = 1.0, 1.0
        else:
            share_a, share_b = 1 / (1 + pair.hedge), pair.hedge / (1 + pair.hedge)
            share_a, share_b = 2 * share_a, 2 * share_b  # Same gross money as the distance method.
        weights[pair.a] += state * share_a / TOP
        weights[pair.b] -= state * share_b / TOP
    return weights, chosen


def strategy_weights(
    method: str, prices: pd.DataFrame, mask: pd.DataFrame, groups: dict[str, str]
) -> tuple[pd.DataFrame, list[int]]:
    """Back-to-back 6-month trading windows, each formed on the 12 months before it. Weights
    are shifted one extra day for the paper's 'wait one day' rule."""
    parts, counts = [], []
    for start in range(0, len(prices) - FORMATION - 20, TRADING):
        weights, chosen = period_weights(method, prices, mask, groups, start)
        parts.append(weights)
        counts.append(len(chosen))
    all_weights = pd.concat(parts).sort_index()
    all_weights = all_weights[~all_weights.index.duplicated()]
    return all_weights.shift(1).fillna(0.0), counts
