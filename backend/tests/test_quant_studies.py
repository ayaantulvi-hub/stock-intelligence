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
