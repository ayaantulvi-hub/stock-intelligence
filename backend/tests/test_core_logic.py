"""Tests for core logic that had no direct tests: why a forecast missed, whether a caution
helped, and the market-wide check. All data here are synthetic test fixtures."""

import numpy as np
import pandas as pd
import pytest

from stockintel import misses, overrides, regime


def test_a_miss_is_explained_by_the_strongest_stored_evidence_first():
    assert misses.reason(0.08, None, 0.02, 0.0, 0.0, ["2.02"]) == misses.RESULTS
    assert misses.reason(-0.03, None, 0.02, -0.02, 0.0, []) == misses.MARKET
    assert misses.reason(-0.03, None, 0.02, 0.0, -0.02, []) == misses.INDUSTRY
    assert misses.reason(0.05, 0.05, 0.02, 0.0, 0.0, []) == misses.GAP
    assert misses.reason(0.07, 0.0, 0.02, 0.0, 0.0, []) == misses.UNKNOWN
    assert misses.reason(0.01, 0.0, 0.02, 0.0, 0.0, []) == misses.NOISE


def test_a_market_move_the_other_way_is_not_used_as_an_excuse():
    # The stock fell while the market rose: the market can't explain it.
    assert misses.reason(-0.07, 0.0, 0.02, 0.02, 0.0, []) == misses.UNKNOWN


def test_a_caution_is_judged_only_with_enough_history_and_a_clear_gap():
    rng = np.random.default_rng(0)
    few = overrides.compare(rng.normal(0, 0.05, 10), rng.normal(0, 0.05, 200))
    assert few["verdict"] == "Not enough history yet" and few["t"] is None
    worse = overrides.compare(rng.normal(-0.03, 0.05, 300), rng.normal(0.0, 0.05, 300))
    assert worse["verdict"].startswith("Helped") and worse["t"] <= -overrides.MIN_T
    same = overrides.compare(rng.normal(0, 0.05, 300), rng.normal(0, 0.05, 300))
    assert same["verdict"] == "No difference shown"


def _market_table(signal_strength: float, seed: int = 1) -> pd.DataFrame:
    """TEST FIXTURE: monthly market readings, with a planted link of chosen strength."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2012-01-02", "2025-12-31")
    reading = pd.Series(rng.normal(0, 1, len(dates)), index=dates).rolling(20).mean().bfill()
    noise = rng.normal(0, 1, len(dates))
    future = signal_strength * reading.to_numpy() + noise * 0.05
    return pd.DataFrame({"reading": reading.to_numpy(), "market_future": future}, index=dates)


def test_market_check_finds_a_planted_link_and_rejects_pure_noise():
    planted = regime.test(_market_table(signal_strength=0.2), first_year=2016)
    assert planted["edge"] is True and planted["t_stat"] >= 3
    noise = regime.test(_market_table(signal_strength=0.0), first_year=2016)
    assert noise["edge"] is False


def test_t_score_is_zero_for_a_single_value():
    assert regime._t(np.array([0.1])) == 0.0


@pytest.mark.xfail(
    strict=True,
    reason="Known bug, not yet fixed (it would change the market check): identical values give "
    "a tiny non-zero spread from rounding, so the t-score comes out near 1e16 instead of 0.",
)
def test_t_score_is_zero_when_every_value_is_the_same():
    assert regime._t(np.array([0.2, 0.2, 0.2])) == 0.0
