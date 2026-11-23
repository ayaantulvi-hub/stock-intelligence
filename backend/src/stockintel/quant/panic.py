"""Market panic detector: do stocks start moving as one before trouble?

Each day, from the last WINDOW days of returns for stocks with a full window:
- average correlation between every pair of stocks;
- top eigenvalue share: how much of all the movement one common force explains;
- absorption ratio (Kritzman, Li, Page & Rigobon): the share of total variance explained by
  the top fifth of eigenvectors. One fifth is a choice made here.
A "shift" is the 15-day average absorption ratio rising at least one standard deviation above
its one-year average, the signal Kritzman and colleagues report came before most of the worst
downturns.

Test: is the equal-weight market's return over the next 21 trading days lower after a shift?
Overlapping 21-day windows are handled with Newey-West standard errors (21 lags). A useful
detector needs t <= -3 on the choice years and a lower average on the held-back years.
"""

import numpy as np
import pandas as pd
import statsmodels.api as sm

from stockintel.quant.evaluate import T_BAR, split

WINDOW = 63  # About a quarter of trading days.
MIN_STOCKS = 30
SHORT, LONG = 15, 252
AHEAD = 21


def readings(returns: pd.DataFrame, step: int = 1) -> pd.DataFrame:
    """Daily correlation readings, each using only the WINDOW days up to and including it."""
    rows = {}
    values = returns.to_numpy()
    for t in range(WINDOW, len(returns) + 1, step):
        window = values[t - WINDOW : t]
        full = ~np.isnan(window).any(axis=0)
        w = window[:, full]
        w = w[:, w.std(axis=0) > 0]
        n = w.shape[1]
        if n < MIN_STOCKS:
            continue
        corr = np.corrcoef(w, rowvar=False)
        eig = np.sort(np.linalg.eigvalsh(corr))[::-1]
        cov_eig = np.sort(np.linalg.eigvalsh(np.cov(w, rowvar=False)))[::-1]
        top = max(1, n // 5)
        rows[returns.index[t - 1]] = {
            "stocks": n,
            "average_correlation": float((corr.sum() - n) / (n * (n - 1))),
            "top_eigenvalue_share": float(eig[0] / n),
            "absorption_ratio": float(cov_eig[:top].sum() / cov_eig.sum()),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def shift_signal(absorption: pd.Series) -> pd.Series:
    """True when the 15-day average is at least 1 standard deviation above the 1-year average."""
    short = absorption.rolling(SHORT).mean()
    long_mean = absorption.rolling(LONG).mean()
    long_sd = absorption.rolling(LONG).std()
    return ((short - long_mean) / long_sd) >= 1.0


def gap_t(ahead: pd.Series, on: pd.Series) -> tuple[float, float]:
    """Regress the next-21-day return on the signal (0 or 1): the slope is the gap after a
    shift, with a Newey-West t-score for overlapping windows."""
    both = pd.concat([ahead, on.astype(float)], axis=1).dropna()
    if len(both) < 60 or both.iloc[:, 1].nunique() < 2:
        return float("nan"), float("nan")
    x = sm.add_constant(both.iloc[:, 1].to_numpy())
    fit = sm.OLS(both.iloc[:, 0].to_numpy(), x).fit(cov_type="HAC", cov_kwds={"maxlags": AHEAD})
    return float(fit.params[1]), float(fit.tvalues[1])


def test(signal: pd.Series, market: pd.Series) -> dict:
    """Next-21-day market return after a shift versus other days."""
    ahead = (1 + market).rolling(AHEAD).apply(np.prod, raw=True).shift(-AHEAD) - 1
    both = pd.concat([signal.astype(float), ahead], axis=1, keys=["on", "ahead"]).dropna()
    early, late = split(both["ahead"])
    out = {}
    for label, part in (("choice", early), ("holdout", late)):
        flag = both["on"].reindex(part.index)
        gap, t = gap_t(part, flag)
        out[label] = {
            "days": len(part),
            "shift_days": int(flag.sum()),
            "gap_after_shift": gap,
            "t": t,
        }
    worst = both["ahead"] <= both["ahead"].quantile(0.05)
    passed = out["choice"]["t"] <= -T_BAR and out["holdout"]["gap_after_shift"] < 0
    return {
        "verdict": "Edge" if passed else "No reliable edge",
        "choice": out["choice"],
        "holdout": out["holdout"],
        "share_of_days_with_shift": float(both["on"].mean()),
        "share_of_worst_5pct_months_after_shift": float(both["on"][worst].mean()),
        "start": both.index.min().date().isoformat(),
        "end": both.index.max().date().isoformat(),
    }
