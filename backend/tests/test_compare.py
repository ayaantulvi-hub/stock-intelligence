"""Model comparison. All prices here are TEST FIXTURES, generated from fixed seeds."""

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel import compare, forecast, queries
from stockintel.market import sessions_between
from stockintel.profiles import PROFILES, TEAM


def panel():
    frames = {}
    for seed in range(20):
        rng = np.random.default_rng(seed)
        days = sessions_between(date(2019, 1, 2), date(2026, 7, 7))
        closes = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.018, len(days))))
        frames[f"S{seed}"] = pd.DataFrame(
            {
                "market_date": days,
                "open": closes,
                "high": closes * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": 1e6,
            }
        )
    slope = pd.Series(0.5, index=pd.date_range("2018-01-01", "2026-07-08"))
    days = pd.date_range("2018-01-01", "2026-07-08")
    vix = pd.DataFrame({"vix": np.random.default_rng(1).uniform(10, 40, len(days))}, index=days)
    return forecast.build_panel(frames, slope, None, vix)


@pytest.fixture(scope="module")
def results():
    return compare.compare(panel(), first_year=2023)


def test_every_model_is_tested_and_described(results):
    assert {row["model"] for row in results} == {*compare.MODELS, TEAM}
    assert set(PROFILES) == {*compare.MODELS, TEAM}


def test_exactly_one_model_is_chosen(results):
    assert sum(row["selected"] for row in results) == 1


def test_random_prices_earn_no_edge(results):
    assert not any(row["edge"] for row in results)


def test_weak_spots_are_measured(results):
    row = results[0]
    assert row["worst_year"] is not None
    assert row["calm_spread"] is not None and row["stressed_spread"] is not None
    assert row["holdout_spread"] is not None


def test_winner_is_chosen_without_seeing_the_final_check():
    good = {"t_stat": 3.5, "holdout_spread": -0.5}
    lucky = {"t_stat": 1.0, "holdout_spread": 0.9}
    assert compare.choose({"A": good, "B": lucky}) == "A"


def base(**changes):
    return {"test_days": 100, "t_stat": 4.0, "spread": 0.01, "holdout_spread": 0.01, **changes}


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({}, True),
        ({"t_stat": 2.9}, False),
        ({"spread": -0.01}, False),
        ({"holdout_spread": -0.01}, False),
        ({"holdout_spread": None}, False),
    ],
)
def test_edge_rules(changes, expected):
    assert compare.has_edge(base(**changes)) is expected


def test_hold_out_dates_do_not_affect_the_score_used_to_choose():
    days = pd.date_range("2024-01-01", periods=40, freq="7D")
    table = pd.DataFrame(
        {"date": days, "gain": np.arange(40) * 0.001, "loss": 0.69, "spread": 0.01, "vix": 15.0}
    )
    changed = table.copy()
    cut = pd.Timestamp("2024-06-01")
    changed.loc[changed["date"] >= cut, "gain"] = -9.0
    assert compare.score(table, cut)["t_stat"] == compare.score(changed, cut)["t_stat"]


def test_champion_defaults_without_an_edge(engine):
    assert forecast.current_champion(engine) == {"model": "Gradient boosting", "edge": False}


def test_latest_comparison_is_served_with_its_cautions(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO model_comparisons (run_at, model, test_days, loss, baseline_loss,
                     t_stat, spread, selected, edge)
                   VALUES (now(), 'Linear model', 50, 0.69, 0.69, 1, 0.01, true, false)"""
            )
        )
    result = queries.model_comparison(engine)
    assert result["models"][0]["caution"]
    assert forecast.current_champion(engine)["model"] == "Linear model"


def test_factor_weights_add_up_to_one():
    weights = compare.factor_weights(panel())
    assert sum(item["weight"] for item in weights) == pytest.approx(1)
    assert "mom_12_1" in {item["factor"] for item in weights}
