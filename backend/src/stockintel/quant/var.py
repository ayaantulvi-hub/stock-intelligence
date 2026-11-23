"""Monte Carlo Value at Risk, and checking it against what really happened.

Each day, 10,000 possible next-day returns are simulated from the past WINDOW days only, and
the 95% Value at Risk is the loss exceeded in 5% of them. A breach is a real next-day return
worse than that. Three ways to simulate:
- historical: draw past days at random (bootstrap);
- normal: draw from a normal curve with the window's mean and standard deviation;
- ewma normal: a normal curve whose volatility weights recent days more (RiskMetrics, 1996,
  decay 0.94 for daily data).
- filtered historical (our version of Hull & White, 1998): each past day's return is divided by
  the EWMA volatility for that day and multiplied by today's, then drawn at random. Real tails,
  current volatility.
- gjr-garch t: volatility that rises more after falls than after gains (Glosten, Jagannathan
  & Runkle, 1993), with fat-tailed Student-t shocks. Fitted by maximum likelihood on the WINDOW
  days before each refit, every GARCH_REFIT days, and run forward on real returns in between.

A correct 95% model is breached on about 5% of days, and breaches don't bunch together.
- Kupiec (1995) proportion-of-failures test: is the breach rate believable?
- Christoffersen (1998) independence test: does one breach make the next more likely?
"""

import math

import numpy as np
import pandas as pd
from arch import arch_model
from scipy.stats import chi2

LEVEL = 0.95
SIMULATIONS = 10_000
WINDOW = 500
EWMA_DECAY = 0.94
GARCH_REFIT = 21  # Refit monthly: a fixed choice to keep the run short, not tuned.


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


def garch_volatility(returns: pd.Series) -> tuple[pd.DataFrame, int]:
    """GJR-GARCH(1,1) with Student-t shocks. For each day t: the mean, volatility and degrees
    of freedom known at the start of day t, from parameters fitted on the WINDOW days before the
    latest refit and real returns up to t-1. Returns (frame, number of fits that failed)."""
    r = returns.to_numpy() * 100  # Percent returns keep the optimiser well scaled.
    n = len(r)
    out = np.full((n, 3), np.nan)
    params = None
    failures = 0
    eps_prev = var_prev = np.nan
    for t in range(WINDOW, n):
        if (t - WINDOW) % GARCH_REFIT == 0:
            try:
                fit = arch_model(
                    r[t - WINDOW : t],
                    mean="Constant",
                    vol="GARCH",
                    p=1,
                    o=1,
                    q=1,
                    dist="t",
                    rescale=False,
                ).fit(disp="off")
                ok = fit.convergence_flag == 0
            except (ValueError, np.linalg.LinAlgError):
                ok = False
            if ok:
                params = fit.params
                eps_prev = r[t - 1] - params["mu"]
                var_prev = float(fit.conditional_volatility[-1]) ** 2
            else:
                failures += 1  # Keep the last good parameters; none yet means no forecast.
        if params is None:
            continue
        down = 1.0 if eps_prev < 0 else 0.0
        var_t = (
            params["omega"]
            + (params["alpha[1]"] + params["gamma[1]"] * down) * eps_prev**2
            + params["beta[1]"] * var_prev
        )
        out[t] = (params["mu"] / 100, math.sqrt(var_t) / 100, params["nu"])
        eps_prev, var_prev = r[t] - params["mu"], var_t
    frame = pd.DataFrame(out, index=returns.index, columns=["mean", "volatility", "dof"])
    return frame, failures


def forecasts(returns: pd.Series, method: str, seed: int = 0) -> pd.Series:
    """Value at Risk for each day (a positive loss), using only the WINDOW days before it."""
    r = returns.dropna()
    rng = np.random.default_rng(seed)
    sd = ewma_volatility(r)
    values = r.to_numpy()
    sd_values = sd.to_numpy()
    garch = garch_volatility(r)[0].to_numpy() if method == "gjr-garch t" else None
    out = np.full(len(r), np.nan)
    for t in range(WINDOW, len(r)):
        if method == "filtered historical":
            past, past_sd = values[t - WINDOW : t], sd_values[t - WINDOW : t]
            standard = (past / past_sd)[np.isfinite(past_sd) & (past_sd > 0)]
            draws = rng.choice(standard, size=SIMULATIONS, replace=True) * sd_values[t]
        elif method == "gjr-garch t":
            mean, vol, dof = garch[t]
            if not np.isfinite(vol):
                continue  # No fitted model yet: no forecast, never a guess.
            shocks = rng.standard_t(dof, SIMULATIONS) * math.sqrt((dof - 2) / dof)
            draws = mean + vol * shocks
        else:
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


def conditional_coverage(hits: np.ndarray, p: float = 1 - LEVEL) -> float:
    """p-value of Christoffersen's (1998) joint test of the breach rate and independence
    (chi-square, 2 df): a two-state Markov chain of breaches against breaches that are
    independent with probability p. Reported alongside the two separate tests; the verdict rule
    is unchanged."""
    h = hits.astype(int)
    prev, cur = h[:-1], h[1:]
    n00 = int(((prev == 0) & (cur == 0)).sum())
    n01 = int(((prev == 0) & (cur == 1)).sum())
    n10 = int(((prev == 1) & (cur == 0)).sum())
    n11 = int(((prev == 1) & (cur == 1)).sum())
    if n00 + n01 == 0 or n10 + n11 == 0:
        return float("nan")

    def ll(prob: float, k0: int, k1: int) -> float:
        return (k0 * math.log(1 - prob) if k0 else 0.0) + (k1 * math.log(prob) if k1 else 0.0)

    pi0, pi1 = n01 / (n00 + n01), n11 / (n10 + n11)
    restricted = ll(p, n00 + n10, n01 + n11)
    free = ll(pi0, n00, n01) + ll(pi1, n10, n11)
    return float(1 - chi2.cdf(-2 * (restricted - free), 2))


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
        "conditional_coverage_p": conditional_coverage(hits),
        "average_var": float(both["var"].mean()),
        "average_excess_loss_on_breach": float(-worst.mean()) if x else 0.0,
        "start": both.index.min().date().isoformat(),
        "end": both.index.max().date().isoformat(),
    }
