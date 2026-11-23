"""Tests for Monte Carlo Value at Risk and its backtests. All data are synthetic fixtures."""

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import chi2

from stockintel.quant import var


def _series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2010-01-01", periods=len(values)))


def test_kupiec_matches_the_likelihood_ratio_written_out():
    n, x, p = 1000, 70, 0.05
    restricted = (n - x) * math.log(1 - p) + x * math.log(p)
    free = (n - x) * math.log(1 - x / n) + x * math.log(x / n)
    expected = 1 - chi2.cdf(-2 * (restricted - free), 1)
    assert var.kupiec(x, n) == pytest.approx(expected)
    assert var.kupiec(50, 1000) == pytest.approx(1.0)  # Exactly the expected rate.


def test_christoffersen_spots_bunched_breaches():
    # Independent 5% breaches over 4,000 days are flagged at close to the 5% false-alarm rate.
    # (With few back-to-back breaches the chi-square approximation is rough: about 8.5% at
    # 1,000 days, 6% at 4,000 in our checks.)
    alarms = [
        var.christoffersen(np.random.default_rng(s).random(4000) < 0.05) < 0.05 for s in range(200)
    ]
    bunched = np.zeros(1000, dtype=bool)
    bunched[100:150] = True  # 5%, all together.
    assert var.christoffersen(bunched) < 0.001
    assert np.mean(alarms) < 0.1


def test_a_correct_model_passes_and_calm_then_wild_data_breaks_the_plain_normal_model():
    rng = np.random.default_rng(4)
    steady = _series(rng.normal(0, 0.01, 2500))
    result = var.backtest(steady, var.forecasts(steady, "normal"))
    assert result["verdict"] == "Not rejected"
    assert result["breach_rate"] == pytest.approx(0.05, abs=0.015)
    # Volatility that comes in waves: the slow normal model is caught out, EWMA copes better.
    vol = np.where((np.arange(2500) // 125) % 2 == 0, 0.005, 0.03)
    waves = _series(rng.normal(0, 1, 2500) * vol)
    plain = var.backtest(waves, var.forecasts(waves, "normal"))
    ewma = var.backtest(waves, var.forecasts(waves, "ewma"))
    assert plain["verdict"].startswith("Rejected")
    assert ewma["christoffersen_p"] > plain["christoffersen_p"]


@pytest.mark.parametrize(
    "method", ["historical", "normal", "ewma", "filtered historical", "gjr-garch t"]
)
def test_value_at_risk_uses_only_earlier_days(method):
    rng = np.random.default_rng(1)
    r = _series(rng.normal(0, 0.01, 800))
    before = var.forecasts(r, method)
    changed = r.copy()
    changed.iloc[700:] = -0.5
    after = var.forecasts(changed, method)
    assert before.iloc[500:701].notna().all()
    pd.testing.assert_series_equal(before.iloc[:701], after.iloc[:701])


def test_verdict_names_the_direction_of_dependence():
    days = pd.bdate_range("2010-01-01", periods=2000)
    returns = pd.Series(0.0, index=days)
    var_level = pd.Series(0.01, index=days)
    bunched = returns.copy()
    bunched.iloc[100:200] = -0.02  # 100 breaches in a row: 5% of days, all together.
    assert var.backtest(bunched, var_level)["verdict"] == "Rejected: breaches bunch together"


def test_conditional_coverage_is_the_sum_of_the_two_separate_tests():
    # Christoffersen (1998): LR_cc = LR_pof + LR_ind, when the rate test uses the same
    # day-to-day transitions as the independence test.
    rng = np.random.default_rng(3)
    hits = rng.random(2000) < 0.06
    later = hits[1:]
    lr_pof = chi2.isf(var.kupiec(int(later.sum()), len(later)), 1)
    lr_ind = chi2.isf(var.christoffersen(hits), 1)
    lr_cc = chi2.isf(var.conditional_coverage(hits), 2)
    assert lr_cc == pytest.approx(lr_pof + lr_ind, rel=1e-6)


def test_conditional_coverage_rejects_bunched_breaches():
    hits = np.zeros(1000, dtype=bool)
    for start in range(0, 1000, 100):
        hits[start : start + 5] = True  # 5% of days, always in runs of five.
    assert var.conditional_coverage(hits) < 0.001


def _gjr_world(days: int, seed: int) -> tuple[pd.Series, np.ndarray]:
    """TEST FIXTURE: returns from a known GJR-GARCH(1,1) with Student-t shocks (dof 6)."""
    rng = np.random.default_rng(seed)
    omega, alpha, gamma, beta, dof = 0.02, 0.03, 0.10, 0.90, 6.0
    variance, eps = omega / (1 - alpha - gamma / 2 - beta), 0.0
    out, vols = np.empty(days), np.empty(days)
    for t in range(days):
        variance = omega + (alpha + gamma * (eps < 0)) * eps**2 + beta * variance
        vols[t] = math.sqrt(variance)
        eps = vols[t] * rng.standard_t(dof) * math.sqrt((dof - 2) / dof)
        out[t] = eps
    return _series(out / 100), vols / 100


def test_garch_tracks_the_true_volatility_of_a_garch_world():
    r, true_vol = _gjr_world(2000, seed=7)
    fitted, failures = var.garch_volatility(r)
    known = fitted["volatility"].notna().to_numpy()
    assert failures == 0
    assert np.corrcoef(fitted["volatility"].to_numpy()[known], true_vol[known])[0, 1] > 0.9


def test_volatility_aware_models_beat_the_plain_normal_model_in_a_garch_world():
    r, _ = _gjr_world(3000, seed=11)
    plain = var.backtest(r, var.forecasts(r, "normal"))
    for method in ("filtered historical", "gjr-garch t"):
        better = var.backtest(r, var.forecasts(r, method))
        assert better["breach_rate"] == pytest.approx(0.05, abs=0.015)
        assert better["breach_rate_after_a_breach"] < plain["breach_rate_after_a_breach"]
