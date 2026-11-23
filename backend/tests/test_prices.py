"""Tests for split and dividend adjustment and the point-in-time size filter.

All prices here are TEST FIXTURES, not market data.
"""

from datetime import date

import pandas as pd
import pytest

from stockintel.market import sessions_between
from stockintel.prices import adjust, eligible_days


def bars(rows):
    days = sessions_between(date(2026, 1, 2), date(2026, 12, 31))[: len(rows)]
    return pd.DataFrame(
        [
            {
                "market_date": day,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": v,
                "div_cash": d,
                "split_factor": s,
            }
            for day, (c, v, d, s) in zip(days, rows, strict=True)
        ]
    )


def test_split_makes_prices_continuous():
    frame = adjust(bars([(100, 10, 0, 1), (100, 10, 0, 1), (50, 20, 0, 2), (50, 20, 0, 1)]))
    assert list(frame["close"]) == [50, 50, 50, 50]
    assert list(frame["volume"]) == [20, 20, 20, 20]


def test_dividend_lowers_earlier_prices_only():
    frame = adjust(bars([(100, 10, 0, 1), (100, 10, 2, 1), (100, 10, 0, 1)]))
    assert frame["close"].iloc[0] == pytest.approx(98)
    assert frame["close"].iloc[1] == 100
    assert list(frame["volume"]) == [10, 10, 10]


def test_a_payout_on_a_reverse_split_day_stays_positive():
    """TEST FIXTURE modelled on Motorola, January 2011: a 1 for 7 split with a spin-off."""
    bars = pd.DataFrame(
        {
            "market_date": [date(2011, 1, 3), date(2011, 1, 4)],
            "open": [9.0, 39.0],
            "high": [9.2, 40.0],
            "low": [8.9, 38.0],
            "close": [9.11, 39.77],
            "volume": [700.0, 100.0],
            "div_cash": [0.0, 27.27375],
            "split_factor": [1.0, 1 / 7],
        }
    )
    result = adjust(bars)
    assert (result[["open", "high", "low", "close"]] > 0).all().all()
    # 63.77 before the split, less the 27.27 payout, leaves 36.50 in today's terms.
    assert result["close"].iloc[0] == pytest.approx(36.50, abs=0.01)


def test_stock_only_counts_after_it_was_large_enough():
    days = pd.Series([date(2020, 1, 15), date(2020, 5, 1), date(2021, 5, 1)])
    # Sized in mid-2019, known from April 2020.
    assert list(eligible_days(days, {2019})) == [False, True, False]
