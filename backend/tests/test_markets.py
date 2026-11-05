"""Market prices. Every response here is a TEST FIXTURE."""

import httpx
import pytest

from stockintel import context
from stockintel.ingest import run_markets
from stockintel.providers.base import FeedError
from stockintel.providers.tiingo import TiingoProvider

ROWS = [
    {
        "ticker": "SPY",
        "timestamp": "2026-11-05T15:00:00+00:00",
        "tngoLast": 495.0,
        "prevClose": 500.0,
    }
]


def provider(rows):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=rows))
    return TiingoProvider("fixture", httpx.Client(transport=transport))


def test_quotes_store_once_and_show_the_days_change(engine):
    assert run_markets(engine, provider(ROWS)) == "ok"
    assert run_markets(engine, provider(ROWS)) == "ok"
    strip = context.market_strip(engine)
    spy = strip["markets"][0]
    assert spy["name"] == "S&P 500"
    assert spy["change"] == pytest.approx(-0.01)
    assert strip["markets"][1]["price"] is None
    assert strip["versus"] is None


def test_a_missing_price_is_an_error_and_not_a_zero():
    with pytest.raises(FeedError):
        provider([{"ticker": "SPY", "timestamp": "2026-11-05T15:00:00+00:00"}]).quotes(("SPY",))
