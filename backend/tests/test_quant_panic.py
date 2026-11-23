"""Tests for the market panic detector. All returns here are synthetic fixtures."""

import numpy as np
import pandas as pd
import pytest

from stockintel.quant import panic


def _returns(common: np.ndarray, stocks: int = 40, seed: int = 0) -> pd.DataFrame:
    """Each stock = common market move * loading + its own noise."""
    rng = np.random.default_rng(seed)
    days = len(common)
    own = rng.normal(0, 0.01, (days, stocks))
    data = common[:, None] + own
    return pd.DataFrame(
        data,
        index=pd.bdate_range("2012-01-02", periods=days),
        columns=[f"S{i}" for i in range(stocks)],
    )


def test_readings_rise_when_stocks_move_together():
    rng = np.random.default_rng(1)
    calm = rng.normal(0, 0.001, 300)
    panic_days = rng.normal(0, 0.03, 300)
    r = _returns(np.concatenate([calm, panic_days]))
    read = panic.readings(r)
    early, late = read.iloc[100:200], read.iloc[-100:]
    for column in ("average_correlation", "top_eigenvalue_share", "absorption_ratio"):
        assert late[column].mean() > early[column].mean() + 0.3
    assert late["average_correlation"].mean() == pytest.approx(0.9, abs=0.05)


def test_readings_use_only_the_window_up_to_each_day():
    rng = np.random.default_rng(2)
    r = _returns(rng.normal(0, 0.01, 300))
    before = panic.readings(r)
    changed = r.copy()
    changed.iloc[200:] = changed.iloc[200:] * 4 + 0.02
    after = panic.readings(changed)
    pd.testing.assert_frame_equal(before.loc[: r.index[199]], after.loc[: r.index[199]])


def test_a_planted_warning_is_found_and_a_random_one_is_not():
    rng = np.random.default_rng(3)
    dates = pd.bdate_range("2010-01-01", "2026-11-20")
    signal = pd.Series(rng.random(len(dates)) < 0.15, index=dates)
    signal = signal.rolling(10).max().fillna(0).astype(bool)  # Signals come in runs.
    noise = pd.Series(rng.normal(0.0004, 0.01, len(dates)), index=dates)
    # Planted: after a signal the market drops 1% a day for the next weeks.
    hurt = noise.copy()
    hurt[signal.shift(1, fill_value=False)] -= 0.01
    assert panic.test(signal, hurt)["verdict"] == "Edge"
    assert panic.test(signal, noise)["verdict"] == "No reliable edge"
