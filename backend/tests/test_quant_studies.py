"""Tests for quant study rules and the shared verdict. All data are synthetic fixtures."""

import numpy as np
import pandas as pd

from stockintel.quant import engine, evaluate, studies


def _prices(days: int = 400, assets: int = 4, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2018-01-01", periods=days)
    steps = rng.normal(0.0003, 0.01, (days, assets))
    return pd.DataFrame(
        100 * np.exp(np.cumsum(steps, axis=0)),
        index=dates,
        columns=[f"S{i}" for i in range(assets)],
    )


def test_equal_weight_spreads_money_over_tradeable_stocks_only():
    mask = pd.DataFrame({"A": [True, True], "B": [True, False]})
    w = studies.equal_weight(mask)
    assert w.loc[0].tolist() == [0.5, 0.5] and w.loc[1].tolist() == [1.0, 0.0]


def test_crossover_holds_only_rising_stocks_and_never_more_than_fully_invested():
    prices = _prices()
    prices["S0"] = np.linspace(
        50, 150, len(prices)
    )  # Always rising: held once both averages exist.
    prices["S1"] = np.linspace(150, 50, len(prices))  # Always falling: never held.
    mask = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    w = studies.ma_crossover(prices, mask)
    assert (w.sum(axis=1) <= 1 + 1e-12).all()
    assert w["S0"].iloc[-1] == 0.25 and w["S1"].iloc[250:].eq(0).all()
    assert w.iloc[:199].eq(0).all().all()  # Nothing before the 200-day average exists.


def test_crossover_rule_does_not_look_ahead():
    prices = _prices()
    mask = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    returns = prices.pct_change()

    def make(r):
        rebuilt = 100 * (1 + r.fillna(0)).cumprod()
        return studies.ma_crossover(rebuilt, mask)

    assert engine.look_ahead_check(make, returns, cut=300)


def test_verdict_finds_a_planted_edge_and_rejects_noise():
    rng = np.random.default_rng(5)
    dates = pd.bdate_range("2015-01-01", "2026-11-20")
    base = pd.Series(rng.normal(0.0003, 0.01, len(dates)), index=dates)
    better = base + 0.001 + rng.normal(0, 0.002, len(dates))
    same = base + rng.normal(0, 0.002, len(dates))
    assert evaluate.judge(better, base)["verdict"] == "Edge"
    assert evaluate.judge(same, base)["verdict"] == "No reliable edge"


def test_hold_out_is_the_last_two_calendar_years():
    dates = pd.bdate_range("2020-01-01", "2026-06-30")
    early, late = evaluate.split(pd.Series(0.0, index=dates))
    assert early.index.max() < pd.Timestamp("2025-01-01") <= late.index.min()


def test_volatility_weights_are_monthly_capped_and_use_only_the_past():
    from stockintel.quant import vol

    rng = np.random.default_rng(2)
    dates = pd.bdate_range("2010-01-01", "2016-12-31")
    calm, wild = rng.normal(0, 0.005, len(dates)), rng.normal(0, 0.03, len(dates))
    excess = pd.Series(np.where(dates.year % 2 == 0, calm, wild), index=dates)
    w = vol.weights(excess, "variance")
    assert w.max() <= vol.MAX_LEVERAGE
    months = w.dropna().groupby(w.dropna().index.to_period("M")).nunique()
    assert (months == 1).all()  # One decision a month.
    assert w["2014-06"].mean() > w["2015-06"].mean()  # More exposure in calm years.
    # Changing everything after a date leaves earlier weights untouched.
    cut = dates.get_loc(pd.Timestamp("2014-03-03"))
    changed = excess.copy()
    changed.iloc[cut + 1 :] *= 5
    pd.testing.assert_series_equal(
        w.iloc[: cut + 1], vol.weights(changed, "variance").iloc[: cut + 1]
    )


def test_alpha_verdict_credits_lower_risk_not_just_higher_return():
    rng = np.random.default_rng(9)
    dates = pd.bdate_range("2012-01-01", "2026-11-20")
    base = pd.Series(rng.normal(0.0003, 0.01, len(dates)), index=dates)
    scaled = 0.5 * base  # Half the risk, half the return: no alpha.
    assert evaluate.judge(scaled, base, by="alpha")["verdict"] == "No reliable edge"
