"""Factor families, the market check and the single decision path.
Every value here is a TEST FIXTURE, generated from fixed seeds."""

from datetime import date

import numpy as np
import pandas as pd
from test_compare import panel

from stockintel import compare, families, forecast, regime, rules


def synthetic(n=6000, seed=0):
    rng = np.random.default_rng(seed)
    x = pd.DataFrame({f: rng.uniform(0, 1, n) for f in families.MEMBERS})
    # Only value (higher is better) and vol_60 (lower is better) really matter.
    signal = 2.0 * (x["value"] - 0.5) - 2.0 * (x["vol_60"] - 0.5)
    y = pd.Series(rng.uniform(0, 1, n) < 1 / (1 + np.exp(-signal)))
    return x, y


def test_only_factors_with_a_clear_effect_count_and_point_the_right_way():
    x, y = synthetic()
    signs = families.directions(x, y)
    assert signs["value"] == 1.0
    assert signs["vol_60"] == -1.0
    noise = [f for f in families.MEMBERS if f not in ("value", "vol_60")]
    assert sum(signs[f] != 0 for f in noise) <= 1  # Noise almost never passes the bar.


def test_family_scores_flip_factors_that_point_down():
    x = pd.DataFrame({"vol_60": [0.9, 0.1], "vol_20": [0.5, 0.5]})
    table = families.scores(x, {"vol_60": -1.0, "vol_20": 0.0})
    assert list(table["Risk"].round(6)) == [0.1, 0.9]
    assert table["Value"].isna().all()


def test_family_models_rank_the_real_signal_and_explain_it():
    x, y = synthetic()
    test_x, test_y = synthetic(seed=1)
    for kind in ("equal", "linear", "boosted"):
        model = families.FamilyModel(kind).fit(x, y)
        chance = model.predict_proba(test_x)[:, 1]
        top = test_y[chance >= np.quantile(chance, 0.8)].mean()
        bottom = test_y[chance <= np.quantile(chance, 0.2)].mean()
        assert top > bottom + 0.15, kind
    model = families.FamilyModel("equal").fit(x, y)
    reasons = families.explain(test_x.iloc[0], model)
    assert {r["family"] for r in reasons} == {"Value", "Risk"}
    assert all(r["push"] in ("buy", "sell", "neutral") for r in reasons)


def test_a_dropped_family_is_left_out():
    x, y = synthetic()
    model = families.FamilyModel("linear", ("Risk",)).fit(x, y)
    assert "Risk" not in model.columns


def test_market_wide_readings_never_reach_the_stock_ranking():
    table = panel()
    columns = forecast.stock_columns(table)
    assert "vix" not in columns and "yield_slope" not in columns
    assert {"curve_tilt", "oil_tilt"} <= set(forecast.LIVE_IDS)


def test_family_test_and_calibration_run_on_random_prices():
    table = panel()
    tests = compare.family_tests(table, first_year=2023)
    assert {row["family"] for row in tests} == set(families.FAMILIES)
    assert all(row["verdict"] in ("Helps", "Hurts", "No clear effect") for row in tests)
    bins = compare.calibration(table, "Families, equal weight")
    assert len(bins) == compare.CALIBRATION_BINS
    assert all(0 <= b["rate"] <= 1 for b in bins)


def test_ranking_becomes_a_plain_chance():
    bins = [(0.0, 0.5, 0.48), (0.5, 1.0, 0.53)]
    assert forecast.beat_chance(bins, 0.9) == 0.53
    assert forecast.beat_chance([], 0.9) is None


def test_market_check_on_random_prices_has_no_edge(engine):
    table = regime.monthly(panel())
    result = regime.test(table, first_year=2022)
    assert result["edge"] is False
    assert regime.state(0.7) == "Favourable" and regime.state(0.3) == "Cautious"
    assert regime.state(None) == "Not verified"


def test_untested_cautions_are_notes_not_overrides(engine):
    assert rules.proven(engine) == {"Expert checks": False, "News warnings": False}
    assert rules.active(engine, date(2026, 11, 9)) == {}
    assert rules.market_hold(engine) is None


def test_a_passed_cautious_market_check_holds_off_buys(engine):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO market_checks (run_at, edge, t_stat, holdout_gain, test_dates,
                     chance, state, readings)
                   VALUES (now(), true, 3.5, 0.01, 120, 0.35, 'Cautious', '[]')"""
            )
        )
    assert "35%" in rules.market_hold(engine)
