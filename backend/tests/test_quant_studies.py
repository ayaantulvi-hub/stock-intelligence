"""Tests for quant study rules and the shared verdict. All data are synthetic fixtures."""

import numpy as np
import pandas as pd
import pytest

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


def test_quant_results_route_returns_the_latest_run_per_variant(engine):
    import json
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import text

    from stockintel import queries

    now = datetime.now(UTC)
    with engine.begin() as conn:
        for at, verdict in ((now - timedelta(days=7), "Edge"), (now, "No reliable edge")):
            conn.execute(
                text(
                    """INSERT INTO quant_results (run_at, study, variant, period, metrics, verdict,
                         settings) VALUES (:at, 'ma_crossover', '50/200', 'p', :m, :v, '{}')"""
                ),
                {"at": at, "m": json.dumps({"verdict": verdict}), "v": verdict},
            )
    rows = queries.quant_results(engine)
    assert len(rows) == 1 and rows[0]["verdict"] == "No reliable edge"


def _waves(seed: int = 5) -> pd.Series:
    """TEST FIXTURE: daily excess returns whose volatility changes every few months."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2008-01-01", "2020-12-31")
    level = np.array([0.004, 0.01, 0.01, 0.01, 0.03])[(np.arange(len(dates)) // 63) % 5]
    return pd.Series(rng.normal(0, 1, len(dates)) * level, index=dates)


@pytest.mark.parametrize("kind", ["conditional", "ewma"])
def test_new_volatility_rules_use_only_the_past(kind):
    from stockintel.quant import vol

    excess = _waves()
    _, held = vol.managed(excess, kind)
    assert held.max() <= vol.MAX_LEVERAGE
    cut = excess.index.get_loc(pd.Timestamp("2016-03-03"))
    changed = excess.copy()
    changed.iloc[cut + 1 :] *= -7
    _, again = vol.managed(changed, kind)
    # Exposure held up to the day after the cut was decided by the cut's close at the latest.
    pd.testing.assert_series_equal(
        held.loc[: excess.index[cut + 1]], again.loc[: excess.index[cut + 1]]
    )


def test_conditional_targeting_leaves_ordinary_months_alone():
    from stockintel.quant import vol

    held = vol.conditional_held(_waves())
    by_month = held.dropna().groupby(held.dropna().index.to_period("M")).first()
    assert (held.dropna().groupby(held.dropna().index.to_period("M")).nunique() == 1).all()
    assert (by_month == 1.0).mean() > 0.4  # Most months are ordinary and stay fully invested.
    assert by_month.min() < 0.6 and by_month.max() > 1.4  # Wild months cut, calm months raised.


def test_daily_ewma_targeting_cuts_exposure_soon_after_volatility_jumps():
    from stockintel.quant import vol

    excess = _waves()
    held = vol.ewma_held(excess).dropna()
    calm_to_wild = excess.index[(np.arange(len(excess)) // 63) % 5 == 4][0:63]
    late = calm_to_wild[-20:]  # The last month of a wild spell, once the estimate has caught up.
    assert held.reindex(late).mean() < 0.6


def _panel(seed: int = 21, days: int = 1300, stocks: int = 40):
    """TEST FIXTURE: invented stocks with different trends and different volatility."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=days)
    drift = np.linspace(-0.001, 0.001, stocks)
    vol = np.linspace(0.005, 0.03, stocks)
    r = pd.DataFrame(
        rng.normal(0, 1, (days, stocks)) * vol + drift,
        index=dates,
        columns=[f"S{i:02d}" for i in range(stocks)],
    )
    return r


@pytest.mark.parametrize("rule", ["momentum", "low_volatility"])
def test_new_stock_rules_use_only_the_past(rule):
    returns = _panel()

    def make(r):
        prices = (1 + r).cumprod()
        return getattr(studies, rule)(prices, pd.DataFrame(True, index=r.index, columns=r.columns))

    assert engine.look_ahead_check(make, returns, cut=900) is True


def test_momentum_buys_last_years_winners_and_ignores_the_latest_month():
    shape = _panel()  # Calm stocks, so each one's trend, not noise, decides the ranking.
    rng = np.random.default_rng(5)
    noise = rng.normal(0, 0.002, shape.shape)
    returns = pd.DataFrame(
        noise + np.linspace(-0.001, 0.001, 40), index=shape.index, columns=shape.columns
    )
    jump = returns.index.get_loc(pd.Timestamp("2018-05-01"))
    returns.iloc[jump : jump + 15, 0] = 0.05  # The worst stock soars in May only.
    prices = (1 + returns).cumprod()
    mask = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    w = studies.momentum(prices, mask)
    end_of_may = w.loc["2018-05"].index[-1]
    held = w.loc[end_of_may]
    assert held.gt(0).sum() == held.lt(0).sum() == 12  # 30% of 40 each side.
    assert held.sum() == pytest.approx(0.0) and held[held > 0].sum() == pytest.approx(1.0)
    assert held["S39"] > 0 and held["S01"] < 0  # Strongest trend long, weakest short.
    assert held["S00"] <= 0  # May's jump is skipped, so it isn't bought.


def test_low_volatility_holds_the_calmest_tenth_and_trades_monthly():
    prices = (1 + _panel()).cumprod()
    mask = pd.DataFrame(True, index=prices.index, columns=prices.columns)
    w = studies.low_volatility(prices, mask)
    live = w[w.sum(axis=1) > 0]
    assert live.index.min() >= prices.index[0] + pd.Timedelta(weeks=156)  # 156 weeks first.
    assert set(live.iloc[-1][live.iloc[-1] > 0].index) == {"S00", "S01", "S02", "S03"}
    assert live.sum(axis=1).round(9).eq(1.0).all()
    changes = live.diff().abs().sum(axis=1)
    month_ends = set(prices.index.to_series().groupby(prices.index.to_period("M")).max())
    assert set(changes[changes > 0].index) <= month_ends
