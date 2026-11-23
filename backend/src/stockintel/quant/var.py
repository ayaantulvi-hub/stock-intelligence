"""Monte Carlo Value at Risk, and checking it against what really happened.

Each day, 10,000 possible next-day returns are simulated from the past WINDOW days only, and
the 95% Value at Risk is the loss exceeded in 5% of them. A breach is a real next-day return
worse than that. Three ways to simulate:
- historical: draw past days at random (bootstrap);
- normal: draw from a normal curve with the window's mean and standard deviation;
- ewma normal: a normal curve whose volatility weights recent days more (RiskMetrics, 1996,
  decay 0.94 for daily data).

A correct 95% model is breached on about 5% of days, and breaches don't bunch together.
- Kupiec (1995) proportion-of-failures test: is the breach rate believable?
- Christoffersen (1998) independence test: does one breach make the next more likely?
"""

import math

import numpy as np
import pandas as pd
from scipy.stats import chi2

LEVEL = 0.95
SIMULATIONS = 10_000
WINDOW = 500
EWMA_DECAY = 0.94


def simulate(
    history: np.ndarray, method: str, rng: np.random.Generator, ewma_sd: float
) -> np.ndarray:
    if method == "historical":
        return rng.choice(history, size=SIMULATIONS, replace=True)
    if method == "normal":
        return rng.normal(history.mean(), history.std(ddof=1), SIMULATIONS)
    return rng.normal(0.0, ewma_sd, SIMULATIONS)  # RiskMetrics assumes a zero mean.


def ewma_volatility(returns: pd.Series, decay: float = EWMA_DECAY) -> pd.Series:
    """sigma^2_t = decay * sigma^2_{t-1} + (1 - decay) * r^2_{t-1}: known at day t's start."""
    r = returns.to_numpy()
    var = np.full(len(r), np.nan)
    seed = np.nanvar(r[:WINDOW]) if len(r) >= WINDOW else np.nan
    for t in range(1, len(r)):
        previous = var[t - 1] if not math.isnan(var[t - 1]) else seed
        var[t] = decay * previous + (1 - decay) * r[t - 1] ** 2
    return pd.Series(np.sqrt(var), index=returns.index)


def forecasts(returns: pd.Series, method: str, seed: int = 0) -> pd.Series:
    """Value at Risk for each day (a positive loss), using only the WINDOW days before it."""
    r = returns.dropna()
    rng = np.random.default_rng(seed)
    sd = ewma_volatility(r)
    values = r.to_numpy()
    out = np.full(len(r), np.nan)
    for t in range(WINDOW, len(r)):
        draws = simulate(values[t - WINDOW : t], method, rng, float(sd.iloc[t]))
        out[t] = -np.quantile(draws, 1 - LEVEL)
    return pd.Series(out, index=r.index)


def kupiec(breaches: int, days: int, p: float = 1 - LEVEL) -> float:
    """p-value of Kupiec's proportion-of-failures likelihood ratio (chi-square, 1 df)."""
    x, n = breaches, days
    if x == 0:
        lr = -2 * n * math.log(1 - p)
    elif x == n:
        lr = -2 * n * math.log(p)
    else:
        lr = -2 * ((n - x) * math.log(n * (1 - p) / (n - x)) + x * math.log(n * p / x))
    return float(1 - chi2.cdf(lr, 1))


def christoffersen(hits: np.ndarray) -> float:
    """p-value of Christoffersen's independence test (chi-square, 1 df)."""
    h = hits.astype(int)
    prev, cur = h[:-1], h[1:]
    n00 = int(((prev == 0) & (cur == 0)).sum())
    n01 = int(((prev == 0) & (cur == 1)).sum())
    n10 = int(((prev == 1) & (cur == 0)).sum())
    n11 = int(((prev == 1) & (cur == 1)).sum())
    if n01 + n11 == 0 or n00 + n01 == 0 or n10 + n11 == 0:
        return float("nan")
    pi0, pi1 = n01 / (n00 + n01), n11 / (n10 + n11)
    pi = (n01 + n11) / (n00 + n01 + n10 + n11)

    def ll(prob: float, k0: int, k1: int) -> float:
        return (k0 * math.log(1 - prob) if k0 else 0.0) + (k1 * math.log(prob) if k1 else 0.0)

    restricted = ll(pi, n00 + n10, n01 + n11)
    free = ll(pi0, n00, n01) + ll(pi1, n10, n11)
    return float(1 - chi2.cdf(-2 * (restricted - free), 1))


def backtest(returns: pd.Series, var: pd.Series) -> dict:
    both = pd.concat([returns, var], axis=1, keys=["r", "var"]).dropna()
    hits = (both["r"] < -both["var"]).to_numpy()
    n, x = len(hits), int(hits.sum())
    p_freq = kupiec(x, n)
    p_ind = christoffersen(hits)
    if p_freq < 0.05:
        verdict = (
            "Rejected: too many breaches" if x / n > 1 - LEVEL else "Rejected: too few breaches"
        )
    elif not math.isnan(p_ind) and p_ind < 0.05:
        # Christoffersen's test is two-sided: breaches can follow each other too often
        # (bunching) or too rarely (the model over-reacts after each one).
        after = hits[1:][hits[:-1]].mean() if hits[:-1].any() else 0.0
        verdict = (
            "Rejected: breaches bunch together"
            if after > x / n
            else "Rejected: breaches avoid each other"
        )
    else:
        verdict = "Not rejected"
    worst = both.loc[hits, "r"] + both.loc[hits, "var"]
    after_breach = hits[1:][hits[:-1]]
    by_year = pd.Series(hits, index=both.index).groupby(both.index.year).mean()
    return {
        "back_to_back_breaches": int((hits[1:] & hits[:-1]).sum()),
        "breach_rate_after_a_breach": float(after_breach.mean()) if len(after_breach) else None,
        "breach_rate_by_year": {str(y): float(v) for y, v in by_year.items()},
        "verdict": verdict,
        "days": n,
        "breaches": x,
        "breach_rate": x / n if n else float("nan"),
        "expected_rate": 1 - LEVEL,
        "kupiec_p": p_freq,
        "christoffersen_p": p_ind,
        "average_var": float(both["var"].mean()),
        "average_excess_loss_on_breach": float(-worst.mean()) if x else 0.0,
        "start": both.index.min().date().isoformat(),
        "end": both.index.max().date().isoformat(),
    }
