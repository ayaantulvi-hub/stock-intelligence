"""Tests for the quant backtest engine and metrics. All data here are synthetic fixtures."""

import math

import empyrical
import numpy as np
import pandas as pd
import pytest

from stockintel.quant import engine, metrics


def _returns(seed: int = 0, days: int = 1000, assets: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", periods=days)
    return pd.DataFrame(
        rng.normal(0.0004, 0.012, (days, assets)),
        index=dates,
        columns=[f"S{i}" for i in range(assets)],
    )


def test_metrics_match_the_independent_empyrical_library():
    r = _returns()["S0"]
    assert metrics.sharpe(r) == pytest.approx(empyrical.sharpe_ratio(r), rel=1e-9)
    assert metrics.max_drawdown(r) == pytest.approx(empyrical.max_drawdown(r), rel=1e-9)
    assert metrics.annual_volatility(r) == pytest.approx(empyrical.annual_volatility(r), rel=1e-9)
    assert metrics.annual_return(r) == pytest.approx(empyrical.annual_return(r), rel=1e-9)


def test_new_ratios_match_empyrical():
    rng = np.random.default_rng(12)
    r = pd.Series(rng.normal(0.0004, 0.011, 1500), index=pd.bdate_range("2015-01-01", periods=1500))
    b = pd.Series(rng.normal(0.0003, 0.010, 1500), index=r.index)
    assert metrics.sortino(r) == pytest.approx(empyrical.sortino_ratio(r), rel=1e-9)
    assert metrics.calmar(r) == pytest.approx(empyrical.calmar_ratio(r), rel=1e-9)
    assert metrics.information_ratio(r, b) == pytest.approx(
        empyrical.excess_sharpe(r, b) * np.sqrt(252), rel=1e-9
    )


def test_worked_examples_from_the_performance_and_risk_skills():
    # historical-risk skill, example 2: NAV 120, 135, 150, 130, 105, 125 -> max drawdown 30%.
    nav = pd.Series([120, 135, 150, 130, 105, 125], index=pd.bdate_range("2020-01-01", periods=6))
    assert metrics.max_drawdown(nav.pct_change().fillna(0)) == pytest.approx(-0.30)
    # performance-metrics skill: a portfolio moving half as much as its benchmark captures
    # 50% of the benchmark's up months and 50% of its down months.
    rng = np.random.default_rng(3)
    days = pd.bdate_range("2018-01-01", periods=750)
    bench = pd.Series(rng.normal(0, 0.01, len(days)), index=days)
    monthly_b = (1 + bench).groupby(days.to_period("M")).prod() - 1
    half = []  # Spread half of each benchmark month evenly over that month's days.
    for month, g in bench.groupby(days.to_period("M")):
        half += [(1 + monthly_b[month] / 2) ** (1 / len(g)) - 1] * len(g)
    up, down = metrics.capture(pd.Series(half, index=days), bench)
    assert up == pytest.approx(0.5) and down == pytest.approx(0.5)


def test_drawdown_by_hand():
    r = pd.Series([0.10, -0.50, 0.20, 1.0], index=pd.bdate_range("2021-01-01", periods=4))
    # Wealth 1.10, 0.55, 0.66, 1.32: deepest fall 0.55 / 1.10 - 1 = -50%, below the peak 2 days.
    assert metrics.max_drawdown(r) == pytest.approx(-0.5)
    assert metrics.longest_drawdown_days(r) == 2


def test_sharpe_standard_error_follows_lo_2002():
    # Annual Sharpe 1.0 over 252 days: daily 1/sqrt(252); SE = sqrt((1 + d^2/2)/252) * sqrt(252).
    daily = 1 / math.sqrt(252)
    expected = math.sqrt((1 + daily**2 / 2) / 252) * math.sqrt(252)
    assert metrics.sharpe_standard_error(1.0, 252) == pytest.approx(expected)
    assert metrics.sharpe_standard_error(1.0, 252) == pytest.approx(1.0, abs=0.01)


def test_weights_earn_the_next_day_and_pay_costs_on_trades():
    dates = pd.bdate_range("2021-01-01", periods=4)
    returns = pd.DataFrame({"A": [0.01, 0.02, -0.03, 0.04]}, index=dates)
    weights = pd.DataFrame({"A": [1.0, 1.0, 0.0, 0.0]}, index=dates)
    result = engine.run(weights, returns, cost_bps=10, borrow_bps=0)
    # Bought at day 0's close: earns day 1 (+2%) and day 2 (-3%); sold at day 2's close.
    assert result.gross.tolist() == pytest.approx([0.0, 0.02, -0.03, 0.0])
    # Costs: 0.10% for buying (paid day 1) and 0.10% for selling (paid day 3).
    assert result.net.tolist() == pytest.approx([0.0, 0.019, -0.03, -0.001])


def test_short_positions_pay_a_borrowing_fee():
    dates = pd.bdate_range("2021-01-01", periods=3)
    returns = pd.DataFrame({"A": [0.0, 0.0, 0.0]}, index=dates)
    weights = pd.DataFrame({"A": [-1.0, -1.0, -1.0]}, index=dates)
    result = engine.run(weights, returns, cost_bps=0, borrow_bps=252)
    assert result.net.iloc[1] == pytest.approx(-0.0001)


def test_planted_look_ahead_is_caught_and_an_honest_rule_passes():
    returns = _returns(days=300)

    def honest(r):  # Momentum: uses only returns up to each day.
        return np.sign(r.rolling(20).sum())

    def cheating(r):  # Peeks at tomorrow's return.
        return np.sign(r.shift(-1))

    assert engine.look_ahead_check(honest, returns, cut=200) is True
    assert engine.look_ahead_check(cheating, returns, cut=200) is False


def test_a_rule_with_no_information_has_no_reliable_sharpe():
    result = engine.run(np.sign(_returns(seed=3).rolling(5).mean()), _returns(seed=4))
    s = result.summary()
    assert abs(s["sharpe_t"]) < 3
