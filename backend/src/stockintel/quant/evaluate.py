"""How a strategy is judged: the same rules for every study.

- Full period: the mean daily gain over the baseline needs a t-score of at least 3, using
  Newey-West standard errors because daily gains are not independent (Harvey, Liu & Zhu argue
  for t > 3 given how many ideas have been tried).
- Hold-out: the last two calendar years are reported separately and must also be positive.
  Parameters are fixed before testing, so no study is tuned on its results.
"""

import math

import numpy as np
import pandas as pd
import statsmodels.api as sm

from stockintel.quant.metrics import relative, summary

T_BAR = 3.0
HOLDOUT_YEARS = 2
NEWEY_WEST_LAGS = 10


def hac_t(values: pd.Series, lags: int = NEWEY_WEST_LAGS) -> float:
    """t-score of the mean of `values`, with Newey-West standard errors."""
    v = values.dropna()
    if len(v) < 30 or v.std() == 0:
        return float("nan")
    fit = sm.OLS(v.to_numpy(), np.ones(len(v))).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(fit.tvalues[0])


def alpha_t(
    strategy: pd.Series, baseline: pd.Series, lags: int = NEWEY_WEST_LAGS
) -> tuple[float, float]:
    """Daily alpha and its t-score from regressing the strategy on the baseline (Newey-West).
    This is how Moreira & Muir judge volatility-managed portfolios."""
    both = pd.concat([strategy, baseline], axis=1).dropna()
    if len(both) < 30:
        return float("nan"), float("nan")
    x = sm.add_constant(both.iloc[:, 1].to_numpy())
    fit = sm.OLS(both.iloc[:, 0].to_numpy(), x).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
    return float(fit.params[0]), float(fit.tvalues[0])


def split(returns: pd.Series) -> tuple[pd.Series, pd.Series]:
    """(choice years, hold-out years): the hold-out is the last two calendar years."""
    last = returns.dropna().index.max().year
    cut = pd.Timestamp(year=last - HOLDOUT_YEARS + 1, month=1, day=1)
    return returns[returns.index < cut], returns[returns.index >= cut]


def judge(strategy: pd.Series, baseline: pd.Series, by: str = "difference") -> dict:
    """Figures for both series and a verdict. `by` is 'difference' (mean gain over the
    baseline) or 'alpha' (regression on the baseline, for strategies that change risk)."""
    early_s, late_s = split(strategy)
    early_b, late_b = split(baseline)
    if by == "alpha":
        gain, t = alpha_t(early_s, early_b)
        late_gain, late_t = alpha_t(late_s, late_b)
    else:
        gain, t = float((early_s - early_b).mean()), hac_t(early_s - early_b)
        late_gain, late_t = float((late_s - late_b).mean()), hac_t(late_s - late_b)
    passed = (not math.isnan(t)) and t >= T_BAR and late_gain > 0
    return {
        "verdict": "Edge" if passed else "No reliable edge",
        "measure": by,
        "choice_gain_daily": gain,
        "choice_t": t,
        "holdout_gain_daily": late_gain,
        "holdout_t": late_t,
        "strategy": summary(strategy),
        "baseline": summary(baseline),
        "relative": relative(strategy, baseline),
        "strategy_holdout": summary(late_s),
        "baseline_holdout": summary(late_b),
    }
