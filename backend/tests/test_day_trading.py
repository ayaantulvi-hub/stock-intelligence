"""The Day trading page. Every bar and response here is a TEST FIXTURE."""

from datetime import UTC, datetime

import httpx
import numpy as np
import pandas as pd
import pytest

from stockintel import day_trading
from stockintel.providers.alpaca import AlpacaProvider
from stockintel.providers.base import FeedError, Provenance

NOW = datetime(2026, 11, 9, 15, 20, tzinfo=UTC)  # 10:20am New York, inside the window.


def test_alpaca_reads_every_page_and_keeps_keys_out_of_urls():
    pages = [
        {
            "bars": {
                "SPY": [{"t": "2026-11-09T14:30:00Z", "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 9}]
            },
            "next_page_token": "abc",
        },
        {
            "bars": {
                "SPY": [{"t": "2026-11-09T14:31:00Z", "o": 1.5, "h": 2, "l": 1, "c": 1.8, "v": 9}],
                "QQQ": [{"t": "2026-11-09T14:30:00Z", "o": 3, "h": 4, "l": 2, "c": 3.5, "v": 9}],
            },
            "next_page_token": None,
        },
    ]
    seen = []

    def answer(request):
        seen.append(request)
        return httpx.Response(200, json=pages[len(seen) - 1])

    source = AlpacaProvider("id", "secret", httpx.Client(transport=httpx.MockTransport(answer)))
    frames, provenance = source.minute_bars(("SPY", "QQQ"), NOW, NOW)
    assert len(frames["SPY"]) == 2 and len(frames["QQQ"]) == 1
    assert seen[1].url.params["page_token"] == "abc"
    assert seen[0].url.params["feed"] == "iex"
    assert "secret" not in str(seen[0].url) and "secret" not in provenance.source_url
    assert str(frames["SPY"]["time"].iloc[0].tz) == "America/New_York"


def test_missing_keys_are_an_error_not_a_fallback():
    with pytest.raises(FeedError, match="ALPACA_API_KEY_ID"):
        AlpacaProvider("", "")


class FixtureSource:
    def __init__(self, frames=None, error=None):
        self.frames, self.error, self.calls = frames, error, 0

    def minute_bars(self, symbols, start, end, timeframe="1Min"):
        self.calls += 1
        if self.error:
            raise FeedError(self.error)
        found = {k: v for k, v in self.frames.items() if k in symbols}
        return found, Provenance("Alpaca (IEX)", "https://fixture.test", NOW, "live")


def minutes(start, n, seed):
    rng = np.random.default_rng(seed)
    closes = 100 + np.cumsum(rng.normal(0, 0.05, n))
    times = pd.date_range(start, periods=n, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {
            "time": times,
            "open": closes,
            "high": closes + 0.05,
            "low": closes - 0.05,
            "close": closes,
            "volume": 1000.0,
        }
    )


def two_days(seed, upto=None):
    frame = pd.concat(
        [minutes("2026-11-06 09:30", 390, seed), minutes("2026-11-09 09:30", 51, seed + 1)],
        ignore_index=True,
    )
    return frame


def test_feed_failure_shows_the_error(engine):
    day_trading._cache.clear()
    result = day_trading.today(engine, FixtureSource(error="Alpaca bars: HTTP 403"), NOW)
    assert result["error"] == "Alpaca bars: HTTP 403"
    assert "stocks" not in result


def test_today_shows_levels_and_only_uses_known_prices(engine):
    day_trading._cache.clear()
    frames = {"SPY": two_days(1), "QQQ": two_days(3)}
    result = day_trading.today(engine, FixtureSource(frames), NOW)
    assert result["session"] == "2026-11-09"
    assert result["stale"] is False and result["market_open"] is True
    spy = result["stocks"][0]
    assert {level["name"] for level in spy["levels"]} >= {"Previous day high", "Previous day low"}
    previous = frames["SPY"][frames["SPY"]["time"].dt.date.astype(str) == "2026-11-06"]
    high = next(level["price"] for level in spy["levels"] if level["name"] == "Previous day high")
    assert high == previous["high"].max()
    for setup in spy["setups"]:
        assert setup["entered_at"] <= NOW.isoformat()


def test_old_bars_during_the_session_are_flagged_and_give_no_setups(engine):
    day_trading._cache.clear()
    frames = {"SPY": two_days(1), "QQQ": two_days(3)}
    later = datetime(2026, 11, 9, 16, 0, tzinfo=UTC)  # 11am New York, last bar 10:20.
    result = day_trading.today(engine, FixtureSource(frames), later)
    assert result["stale"] is True
    assert all(stock["setups"] == [] for stock in result["stocks"])


def test_a_test_run_stores_only_a_summary_and_needs_an_edge(engine):
    frames = {"SPY": two_days(5), "QQQ": two_days(7)}
    result = day_trading.run_test(engine, FixtureSource(frames), 1, NOW)
    assert result["verdict"] == "No reliable edge"  # Far too few trades to show anything.
    stored = day_trading.latest_test(engine)
    assert stored["verdict"] == "No reliable edge"
    assert stored["source"] == "Alpaca (IEX)"


def test_verdict_needs_enough_trades_and_to_beat_chance():
    good = [
        {
            "r": 1.0 + 0.1 * (i % 3),
            "random_r": -0.1,
            "confirmed_by": "x",
            "level": "y",
            "symbol": "SPY",
            "entered": "2024-01-02T15:00:00Z",
        }
        for i in range(40)
    ]
    assert day_trading.verdict(good)["verdict"] == "Edge shown in test"
    assert day_trading.verdict(good[:10])["verdict"] == "No reliable edge"
    worse_than_chance = [{**row, "random_r": 5.0} for row in good]
    assert day_trading.verdict(worse_than_chance)["verdict"] == "No reliable edge"


class ByTimeframe(FixtureSource):
    def minute_bars(self, symbols, start, end, timeframe="1Min"):
        self.calls += 1
        frames = self.frames[timeframe]
        found = {
            k: v[(v["time"] >= start) & (v["time"] < end)]
            for k, v in frames.items()
            if k in symbols
        }
        return found, Provenance("Alpaca (IEX)", "https://fixture.test", NOW, "live")


def test_scanner_finds_breakouts_maps_symbols_and_skips_the_forming_bar(engine):
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('BRK-B', '1', 'Berkshire', 'NYSE', 1), ('FLAT', '2', 'Flat', 'NYSE', 2)"""
            )
        )
    times = pd.date_range("2026-11-09 09:30", periods=11, freq="5min", tz="America/New_York")
    up = [100, 101, 99.5, 100.5, 100.4, 100.6, 100.5, 100.7, 100.6, 100.5, 103.0]
    breakout = pd.DataFrame(
        {
            "time": times,
            "open": up,
            "high": [c + 0.2 for c in up],
            "low": [c - 0.2 for c in up],
            "close": up,
            "volume": 1e5,
        }
    )
    flat = breakout.assign(open=100.0, high=100.2, low=99.8, close=100.0)
    source = ByTimeframe({"5Min": {"BRK.B": breakout, "FLAT": flat}})
    # 10:23 New York: the 10:20 bar (the jump to 103) is still forming, so it must be ignored.
    result = day_trading.scan_orb(
        engine, source, times[0].date(), datetime(2026, 11, 9, 15, 23, tzinfo=UTC)
    )
    assert result["scanned"] == 2 and result["found"] == 0
    later = datetime(2026, 11, 9, 15, 26, tzinfo=UTC)
    result = day_trading.scan_orb(engine, source, times[0].date(), later)
    assert [hit["ticker"] for hit in result["setups"]] == ["BRK-B"]
    assert result["setups"][0]["side"] == "long" and result["setups"][0]["entry"] == 103.0
    assert result["setups"][0]["replay"] is None  # Too little history for 10,000 replays.
