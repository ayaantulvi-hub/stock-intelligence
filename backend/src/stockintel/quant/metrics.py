"""Performance measures written from first principles. Tests check them against empyrical.

All functions take simple daily returns (0.01 = +1%) and assume 252 trading days a year.
"""

import math

import numpy as np
import pandas as pd

DAYS_PER_YEAR = 252


def annual_return(returns: pd.Series) -> float:
    """Compound growth rate a year: the constant yearly rate that gives the same end value."""
    r = returns.dropna()
    if r.empty:
        return float("nan")
    growth = float(np.prod(1 + r.to_numpy()))
    return growth ** (DAYS_PER_YEAR / len(r)) - 1


def annual_volatility(returns: pd.Series) -> float:
    """Standard deviation of daily returns, scaled by the square root of 252."""
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    return float(r.std(ddof=1)) * math.sqrt(DAYS_PER_YEAR)


def sharpe(returns: pd.Series, risk_free_daily: float = 0.0) -> float:
    """Average excess return over its standard deviation, scaled to a year by the square root
    of 252. Lo (2002) shows this scaling is exact only for returns with no serial correlation."""
    r = returns.dropna() - risk_free_daily
    if len(r) < 2 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1)) * math.sqrt(DAYS_PER_YEAR)


def sharpe_standard_error(annual_sharpe: float, days: int) -> float:
    """Standard error of an annualised Sharpe ratio for independent, identically distributed
    returns (Lo 2002): sqrt((1 + SR_d^2 / 2) / T), with SR_d the daily ratio, then annualised."""
    if days < 2 or math.isnan(annual_sharpe):
        return float("nan")
    daily = annual_sharpe / math.sqrt(DAYS_PER_YEAR)
    return math.sqrt((1 + daily**2 / 2) / days) * math.sqrt(DAYS_PER_YEAR)


def drawdown(returns: pd.Series) -> pd.Series:
    """Fall from the highest value reached so far, at each date (0 at a new high, -0.2 = 20%)."""
    wealth = (1 + returns.fillna(0)).cumprod()
    peak = np.maximum(wealth.cummax(), 1.0)
    return wealth / peak - 1


def max_drawdown(returns: pd.Series) -> float:
    """The largest fall from a peak, as a negative number."""
    dd = drawdown(returns)
    return float(dd.min()) if len(dd) else float("nan")


def longest_drawdown_days(returns: pd.Series) -> int:
    """Most trading days spent below a previous high."""
    below = (drawdown(returns) < 0).to_numpy()
    longest = run = 0
    for flag in below:
        run = run + 1 if flag else 0
        longest = max(longest, run)
    return longest


def downside_deviation(returns: pd.Series, mar: float = 0.0) -> float:
    """Annualised root-mean-square of returns below a minimum acceptable return (MAR, daily)."""
    r = returns.dropna()
    if len(r) < 2:
        return float("nan")
    below = np.minimum(r - mar, 0.0)
    return float(np.sqrt((below**2).mean())) * math.sqrt(DAYS_PER_YEAR)


def sortino(returns: pd.Series, mar: float = 0.0) -> float:
    """Annualised mean return above the MAR over the downside deviation below the SAME MAR, so
    numerator and denominator share one reference point (Sortino & Price, 1994)."""
    r = returns.dropna()
    dd = downside_deviation(r, mar)
    if len(r) < 2 or not dd:
        return float("nan")
    return float((r - mar).mean() * DAYS_PER_YEAR / dd)


def calmar(returns: pd.Series) -> float:
    """Compound annual return over the size of the worst drawdown."""
    mdd = max_drawdown(returns)
    return annual_return(returns) / abs(mdd) if mdd and not math.isnan(mdd) else float("nan")


def information_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    """Annualised active return over annualised tracking error."""
    active = (returns - benchmark).dropna()
    if len(active) < 2 or active.std(ddof=1) == 0:
        return float("nan")
    return float(active.mean() / active.std(ddof=1)) * math.sqrt(DAYS_PER_YEAR)


def capture(returns: pd.Series, benchmark: pd.Series) -> tuple[float, float]:
    """(up capture, down capture): the strategy's average monthly return in the benchmark's
    up months over the benchmark's, and the same for down months. Below 1 on the down side
    means it lost less than the benchmark when the benchmark fell."""
    both = pd.concat([returns, benchmark], axis=1, keys=["s", "b"]).dropna()
    if both.empty:
        return float("nan"), float("nan")
    monthly = (1 + both).groupby(both.index.to_period("M")).prod() - 1
    up, down = monthly[monthly["b"] > 0], monthly[monthly["b"] < 0]
    ratio = lambda part: float(part["s"].mean() / part["b"].mean()) if len(part) else float("nan")
    return ratio(up), ratio(down)


def relative(returns: pd.Series, benchmark: pd.Series) -> dict:
    """Figures that only make sense against a benchmark that moves (not a zero line)."""
    b = benchmark.dropna()
    if b.empty or (b == 0).all():
        return {}
    up, down = capture(returns, benchmark)
    return {
        "information_ratio": information_ratio(returns, benchmark),
        "up_capture": up,
        "down_capture": down,
    }


def summary(returns: pd.Series, turnover: pd.Series | None = None) -> dict:
    """The standard figures for one strategy, with the Sharpe ratio's uncertainty."""
    r = returns.dropna()
    sr = sharpe(r)
    se = sharpe_standard_error(sr, len(r))
    return {
        "days": len(r),
        "start": r.index.min().date().isoformat() if len(r) else None,
        "end": r.index.max().date().isoformat() if len(r) else None,
        "annual_return": annual_return(r),
        "annual_volatility": annual_volatility(r),
        "sharpe": sr,
        "sharpe_se": se,
        "sharpe_t": sr / se if se and not math.isnan(se) else float("nan"),
        "sortino": sortino(r),
        "calmar": calmar(r),
        "max_drawdown": max_drawdown(r),
        "longest_drawdown_days": longest_drawdown_days(r),
        "hit_rate": float((r > 0).mean()) if len(r) else float("nan"),
        "annual_turnover": float(turnover.mean() * DAYS_PER_YEAR) if turnover is not None else None,
    }
