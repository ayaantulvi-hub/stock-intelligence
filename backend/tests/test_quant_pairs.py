"""Tests for the pairs trading study. All prices here are synthetic fixtures."""

import numpy as np
import pandas as pd
import pytest

from stockintel.quant import pairs


def _universe(seed: int = 0, days: int = 700) -> pd.DataFrame:
    """Four random-walk stocks plus a planted cointegrated pair (TWIN tracks BASE)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=days)
    walks = {f"R{i}": 50 * np.exp(np.cumsum(rng.normal(0, 0.015, days))) for i in range(4)}
    base = 40 * np.exp(np.cumsum(rng.normal(0, 0.015, days)))
    noise = np.zeros(days)
    for t in range(1, days):  # A spread that keeps pulling back to zero.
        noise[t] = 0.85 * noise[t - 1] + rng.normal(0, 0.02)
    walks["BASE"] = base
    walks["TWIN"] = base * np.exp(noise) * 1.3
    return pd.DataFrame(walks, index=dates)


def test_cointegration_finds_the_planted_pair_and_estimates_its_hedge():
    prices = _universe()
    groups = dict.fromkeys(prices.columns, "36")
    found = pairs.coint_pairs(prices.iloc[:252], groups)
    assert (found[0].a, found[0].b) in {("BASE", "TWIN"), ("TWIN", "BASE")}
    assert found[0].hedge == pytest.approx(1.0, abs=0.1)
    assert found[0].score < 0.01


def test_pairs_only_form_within_an_industry():
    prices = _universe()
    groups = {"BASE": "36", "TWIN": "28", "R0": "36", "R1": "36", "R2": "10", "R3": "10"}
    names = {frozenset((p.a, p.b)) for p in pairs.distance_pairs(prices.iloc[:252], groups)}
    assert frozenset(("BASE", "TWIN")) not in names
    assert all(groups[a] == groups[b] for a, b in names)


def test_positions_open_beyond_two_close_at_the_cross_and_on_the_last_day():
    gap = pd.Series([0.0, 1.5, 2.5, 1.0, 0.3, -0.2, -2.4, -1.0, -0.5])
    assert pairs.positions(gap).tolist() == [0, 0, -1, -1, -1, 0, 1, 1, 0]
    assert pairs.positions(pd.Series([0.0, 2.5, np.nan, 2.5])).tolist() == [0, -1, 0, 0]


def test_planted_pair_makes_money_before_costs_and_rules_do_not_look_ahead():
    from stockintel.quant import engine

    prices = _universe(days=900)
    mask = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    groups = dict.fromkeys(prices.columns, "36")
    weights, counts = pairs.strategy_weights("cointegration", prices, mask, groups)
    returns = prices.pct_change()
    result = engine.run(weights, returns, cost_bps=0, borrow_bps=0)
    assert result.gross.sum() > 0 and counts

    def make(r):
        rebuilt = 50 * (1 + r.fillna(0)).cumprod()
        return (
            pairs.strategy_weights("distance", rebuilt, mask, groups)[0].reindex(r.index).fillna(0)
        )

    assert engine.look_ahead_check(make, returns, cut=500)
