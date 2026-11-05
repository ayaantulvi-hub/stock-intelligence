"""Fibonacci levels. Every candle here is a TEST FIXTURE."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from stockintel import charts, context, experts
from stockintel.providers.tiingo import TiingoProvider


def bars(closes):
    start = date(2026, 1, 1)
    closes = np.array(closes, dtype=float)
    return pd.DataFrame(
        {
            "market_date": [start + timedelta(days=i) for i in range(len(closes))],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": 1.0,
        }
    )


def rise_then(end):
    return bars([*np.linspace(100, 200, 100), *np.linspace(200, end, 20)])


def test_levels_of_a_rise_measure_down_from_the_high():
    found = charts.fibonacci(rise_then(150))
    assert found["rising"] is True
    prices = {item["ratio"]: item["price"] for item in found["levels"]}
    assert prices[0.5] == pytest.approx(150)
    assert prices[0.618] == pytest.approx(138.2)
    assert found["pullback"] == pytest.approx(0.5)
    assert found["near"]["ratio"] == 0.5


def test_levels_of_a_fall_measure_up_from_the_low():
    found = charts.fibonacci(bars([*np.linspace(200, 100, 100), *np.linspace(100, 150, 20)]))
    assert found["rising"] is False
    assert found["levels"][2]["price"] == pytest.approx(150)


def test_too_little_history_gives_nothing():
    assert charts.fibonacci(bars([100.0] * 10)) is None


def test_score_rewards_closeness_and_uses_no_later_candles():
    table = rise_then(150)
    score = charts.fib_score(table, 120)
    assert score.iloc[-1] == pytest.approx(0, abs=0.01)
    longer = bars([*table["close"], 400.0, 500.0])
    assert charts.fib_score(longer, 120).iloc[len(table) - 1] == score.iloc[-1]


def test_fibonacci_lens_verdicts():
    assert experts.fibonacci_lens(rise_then(150))["verdict"] == experts.GOOD
    assert experts.fibonacci_lens(rise_then(105))["verdict"] == experts.BAD
    assert experts.fibonacci_lens(bars([100.0] * 10))["verdict"] == experts.UNKNOWN


def test_market_lens():
    assert experts.market_lens({"above_200": True, "month": 0.02})["verdict"] == experts.GOOD
    assert experts.market_lens({"above_200": False, "month": -0.05})["verdict"] == experts.BAD
    assert experts.market_lens(None)["verdict"] == experts.UNKNOWN


def test_market_note_says_not_verified_with_no_data(engine):
    assert context.market_note(engine) == "Whole market: Not verified."


def test_quote_times_with_nanoseconds_are_read():
    import httpx

    rows = [
        {
            "ticker": "SPY",
            "timestamp": "2026-11-05T10:12:17.736273854-05:00",
            "tngoLast": 750.0,
            "prevClose": 760.0,
        }
    ]
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=rows)))
    assert TiingoProvider("fixture", client).quotes(("SPY",))[0][0].price == 750.0
