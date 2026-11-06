"""Ingestion against a real test database. All provider data here is a labelled TEST FIXTURE."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from stockintel import market, queries
from stockintel.ingest import run_economic, run_filings, run_prices, run_universe
from stockintel.providers.base import (
    FeedError,
    Filing,
    Listing,
    Observation,
    PriceBar,
    Provenance,
    RateLimited,
)
from stockintel.providers.fred import FredProvider
from stockintel.providers.sec import SecProvider
from stockintel.providers.tiingo import TiingoProvider

NOW = datetime(2026, 7, 8, 12, tzinfo=UTC)  # A Wednesday, so Tuesday 7 July is the last session.
START = date(2026, 6, 30)
SESSIONS = [
    date(2026, 6, 30),
    date(2026, 7, 1),
    date(2026, 7, 2),
    date(2026, 7, 6),
    date(2026, 7, 7),
]


def provenance(name="Tiingo", url="https://fixture.test/prices"):
    return Provenance(name, url, NOW, "end_of_day")


def bar(day, close=100.0, **changes):
    fields = {
        "open": 99.0,
        "high": max(101.0, close),
        "low": 98.0,
        "close": close,
        "volume": 1000.0,
        "div_cash": 0.0,
        "split_factor": 1.0,
    }
    return PriceBar(market_date=day, **{**fields, **changes})


class FixtureSec:
    def __init__(self, listings=None, error=None):
        self._listings, self.error = listings, error

    def listings(self):
        if self.error:
            raise self.error
        return self._listings, provenance("SEC EDGAR")

    def filings(self, cik):
        if self.error:
            raise self.error
        filing = Filing(
            "0000000001-26-000001",
            "10-Q",
            date(2026, 5, 1),
            date(2026, 3, 31),
            None,
            "https://fixture.test/doc.htm",
        )
        return [filing], provenance("SEC EDGAR", "https://fixture.test/submissions")


class FixturePrices:
    def __init__(self, bars=None, errors=None):
        self.bars, self.errors = bars if bars is not None else {}, errors or {}
        self.calls = []

    def daily_bars(self, ticker, start, end):
        self.calls.append((ticker, start, end))
        if ticker in self.errors:
            raise self.errors[ticker]
        return self.bars.get(ticker, []), provenance()


class FixtureFred:
    def __init__(self, error=None):
        self.error = error
        self.fetches = 0
        self.revision = 0.0

    def observations(self, series_id, start, all_versions=True):
        if self.error:
            raise self.error
        if not all_versions:
            day = (NOW.date() - date(2026, 1, 1)).days + self.fetches
            self.fetches += 1
            published = date(2026, 1, 1) + timedelta(days=day)
            value = 4.0 + self.revision
            return [Observation(date(2026, 1, 1), published, value)], provenance(
                "FRED", "https://fixture.test/fred"
            )
        return [
            Observation(date(2026, 1, 1), date(2026, 2, 1), 1.0),
            Observation(date(2026, 1, 1), date(2026, 3, 1), 1.1),
            Observation(date(2026, 2, 1), date(2026, 3, 1), None),
        ], provenance("FRED", "https://fixture.test/fred")


@pytest.fixture
def stocks(engine):
    listings = [
        Listing("AAA", 1, "Aaa Inc", "NYSE"),
        Listing("OTC", 2, "Skip", "OTC"),
        Listing("AAB", 1, "Aaa Inc", "NYSE"),
        Listing("BBB", 3, "Bbb Inc", "Nasdaq"),
    ]
    assert run_universe(engine, FixtureSec(listings), 2) == "ok"
    return engine


def scalar(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def last_run(engine, feed):
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT * FROM feed_runs WHERE feed = :f ORDER BY id DESC LIMIT 1"), {"f": feed}
        ).first()


def test_universe_filters_exchanges_and_duplicate_companies(stocks):
    with stocks.connect() as conn:
        assert list(
            conn.execute(text("SELECT ticker FROM securities ORDER BY universe_rank")).scalars()
        ) == ["AAA", "BBB"]


def test_universe_stays_fixed_once_chosen(stocks):
    assert run_universe(stocks, FixtureSec([Listing("NEW", 9, "New", "NYSE")]), 1) == "ok"
    assert scalar(stocks, "SELECT count(*) FROM securities") == 2


def test_stored_price_shows_source_and_timestamps(stocks):
    provider = FixturePrices({"AAA": [bar(d) for d in SESSIONS], "BBB": [bar(d) for d in SESSIONS]})
    assert run_prices(stocks, provider, START, 45, NOW) == "ok"
    latest = queries.stock(stocks, "AAA")["bars"][0]
    assert latest["market_date"] == date(2026, 7, 7)
    assert latest["market_timestamp"] == datetime(2026, 7, 7, 20, tzinfo=UTC)  # 4pm New York
    assert latest["source"] == "Tiingo"
    assert latest["source_url"] == "https://fixture.test/prices"
    assert latest["retrieved_at"] == NOW
    assert latest["data_status"] == "end_of_day"


def test_early_close_uses_the_real_closing_time():
    assert market.session_close(date(2025, 7, 3)) == datetime(2025, 7, 3, 17, tzinfo=UTC)


def test_failed_feed_stores_nothing_and_reports_the_error(stocks):
    provider = FixturePrices(
        errors={"AAA": FeedError("Tiingo AAA: HTTP 500"), "BBB": FeedError("Tiingo BBB: HTTP 500")}
    )
    assert run_prices(stocks, provider, START, 45, NOW) == "error"
    assert scalar(stocks, "SELECT count(*) FROM price_bars") == 0
    feed = next(item for item in queries.feeds(stocks) if item["feed"] == "prices")
    assert feed["status"] == "error"
    assert "HTTP 500" in feed["message"]


def test_one_failed_stock_is_partial_and_the_other_is_kept(stocks):
    provider = FixturePrices(
        {"BBB": [bar(d) for d in SESSIONS]}, {"AAA": FeedError("Tiingo AAA: HTTP 404")}
    )
    assert run_prices(stocks, provider, START, 45, NOW) == "partial"
    assert last_run(stocks, "prices").items_ok == 1


def test_rate_limit_stops_the_run(stocks):
    provider = FixturePrices(errors={"AAA": RateLimited("Tiingo: rate limit")})
    assert run_prices(stocks, provider, START, 45, NOW) == "error"
    assert len(provider.calls) == 1


def test_correction_adds_a_row_and_keeps_the_old_value(stocks):
    run_prices(
        stocks,
        FixturePrices({"AAA": [bar(d) for d in SESSIONS], "BBB": [bar(d) for d in SESSIONS]}),
        START,
        45,
        NOW,
    )
    later = datetime(2026, 7, 9, 12, tzinfo=UTC)
    corrected = [bar(d) for d in SESSIONS[:-1]] + [bar(SESSIONS[-1], close=100.5)]
    run_prices(stocks, FixturePrices({"AAA": corrected}), START, 1, later)
    assert (
        scalar(
            stocks,
            "SELECT count(*) FROM price_bars WHERE market_date = '2026-07-07' AND security_id = 1",
        )
        == 2
    )
    assert queries.stock(stocks, "AAA")["bars"][0]["close"] == 100.5


def test_unchanged_bars_are_not_stored_again(stocks):
    bars = {"AAA": [bar(d) for d in SESSIONS], "BBB": [bar(d) for d in SESSIONS]}
    run_prices(stocks, FixturePrices(bars), START, 45, NOW)
    count = scalar(stocks, "SELECT count(*) FROM price_bars")
    run_prices(stocks, FixturePrices(bars), START, 45, datetime(2026, 7, 9, 12, tzinfo=UTC))
    assert scalar(stocks, "SELECT count(*) FROM price_bars") == count


def test_impossible_bar_is_rejected_and_logged(stocks):
    bad = bar(SESSIONS[0], low=500.0)
    run_prices(stocks, FixturePrices({"AAA": [bad]}), START, 45, NOW)
    assert scalar(stocks, "SELECT count(*) FROM price_bars") == 0
    assert scalar(stocks, "SELECT count(*) FROM validation_issues WHERE kind = 'invalid'") == 1


def test_gap_is_flagged_and_not_filled(stocks):
    bars = [bar(d) for d in SESSIONS if d != date(2026, 7, 2)]
    run_prices(stocks, FixturePrices({"AAA": bars}), START, 45, NOW)
    assert scalar(stocks, "SELECT count(*) FROM price_bars") == 4
    assert scalar(stocks, "SELECT market_date FROM validation_issues WHERE kind = 'gap'") == date(
        2026, 7, 2
    )


def test_holiday_is_not_a_gap(stocks):
    bars = [bar(date(2026, 7, 2)), bar(date(2026, 7, 6))]  # 3 July 2026 is a market holiday.
    run_prices(stocks, FixturePrices({"AAA": bars}), START, 45, NOW)
    assert scalar(stocks, "SELECT count(*) FROM validation_issues WHERE kind = 'gap'") == 0


def test_large_move_is_flagged_unless_it_is_a_split(stocks):
    moved = [bar(SESSIONS[0]), bar(SESSIONS[1], close=200.0)]
    split = [
        bar(SESSIONS[0]),
        bar(SESSIONS[1], close=50.0, split_factor=0.5, high=100.0, low=40.0, open=45.0),
    ]
    run_prices(stocks, FixturePrices({"AAA": moved, "BBB": split}), START, 45, NOW)
    with stocks.connect() as conn:
        assert list(
            conn.execute(
                text("SELECT ticker FROM validation_issues WHERE kind='outlier'")
            ).scalars()
        ) == ["AAA"]


def test_no_bars_is_logged_as_missing(stocks):
    run_prices(stocks, FixturePrices({}), START, 45, NOW)
    assert scalar(stocks, "SELECT count(*) FROM validation_issues WHERE kind = 'missing'") == 2


def test_stale_data_is_flagged(stocks):
    run_prices(stocks, FixturePrices({"AAA": [bar(date(2020, 1, 2))]}), date(2020, 1, 1), 45, NOW)
    assert queries.stock(stocks, "AAA")["stale"] is True


@pytest.mark.parametrize("table", ["price_bars", "fetches"])
def test_stored_records_cannot_be_changed(stocks, table):
    run_prices(stocks, FixturePrices({"AAA": [bar(SESSIONS[0])]}), START, 45, NOW)
    for statement in (
        f"DELETE FROM {table}",
        f"UPDATE {table} SET fetch_id = 1"
        if table == "price_bars"
        else f"UPDATE {table} SET source_url = 'x'",
    ):
        with pytest.raises(DBAPIError, match="append-only"), stocks.begin() as conn:
            conn.execute(text(statement))


def test_filings_are_stored_once_with_provenance(stocks):
    assert run_filings(stocks, FixtureSec(), NOW) == "ok"
    assert run_filings(stocks, FixtureSec(), NOW) == "ok"
    assert scalar(stocks, "SELECT count(*) FROM filings") == 2
    filing = queries.stock(stocks, "AAA")["filings"][0]
    assert filing["source"] == "SEC EDGAR"
    assert filing["source_url"] == "https://fixture.test/submissions"


def test_failed_filings_feed_reports_error(stocks):
    assert run_filings(stocks, FixtureSec(error=FeedError("SEC CIK 1: HTTP 503")), NOW) == "error"
    assert scalar(stocks, "SELECT count(*) FROM filings") == 0


def test_economic_keeps_every_version_and_missing_stays_missing(engine):
    assert run_economic(engine, FixtureFred()) == "ok"
    assert (
        scalar(
            engine,
            "SELECT count(DISTINCT value) FROM economic_observations "
            "WHERE series_id = 'UNRATE' AND observation_date = '2026-01-01'",
        )
        == 2
    )
    latest = next(row for row in queries.economic(engine) if row["series_id"] == "CPIAUCSL")
    assert latest["value"] is None
    assert latest["source"] == "FRED"
    count = scalar(engine, "SELECT count(*) FROM economic_observations")
    run_economic(engine, FixtureFred())
    assert scalar(engine, "SELECT count(*) FROM economic_observations") == count


def test_daily_series_stores_a_new_row_only_when_a_value_changes(engine):
    provider = FixtureFred()
    run_economic(engine, provider)
    run_economic(engine, provider)
    daily = "SELECT count(*) FROM economic_observations WHERE series_id = 'DGS10'"
    assert scalar(engine, daily) == 1
    provider.revision = 0.1
    run_economic(engine, provider)
    assert scalar(engine, daily) == 2


def test_failed_economic_feed_reports_error(engine):
    assert run_economic(engine, FixtureFred(FeedError("FRED DGS10: HTTP 400"))) == "error"
    assert scalar(engine, "SELECT count(*) FROM economic_observations") == 0


def test_missing_key_is_an_error_not_a_fallback():
    with pytest.raises(FeedError):
        TiingoProvider("")
    with pytest.raises(FeedError):
        FredProvider("")
    with pytest.raises(FeedError):
        SecProvider("")


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_tiingo_parses_and_keeps_the_token_out_of_the_url():
    seen = {}

    def handler(request):
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(
            200,
            json=[
                {
                    "date": "2026-07-07T00:00:00.000Z",
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 10,
                    "divCash": 0,
                    "splitFactor": 1,
                    "adjClose": 1.5,
                }
            ],
        )

    bars, source = TiingoProvider("secret-token", client(handler)).daily_bars(
        "BRK-B", date(2026, 7, 1), date(2026, 7, 7)
    )
    assert bars[0].close == 1.5
    assert seen["auth"] == "Token secret-token"
    assert "secret-token" not in source.source_url and "brk-b" in source.source_url


def test_fred_keeps_the_key_out_of_the_stored_url():
    payload = {
        "observations": [{"date": "2026-01-01", "realtime_start": "2026-02-01", "value": "."}]
    }
    rows, source = FredProvider(
        "secret-key", client(lambda r: httpx.Response(200, json=payload))
    ).observations("DGS10", date(2026, 1, 1))
    assert rows[0].value is None
    assert "secret-key" not in source.source_url


@pytest.mark.parametrize("status, error", [(500, FeedError), (429, RateLimited)])
def test_http_failures_raise(status, error):
    provider = TiingoProvider("x", client(lambda r: httpx.Response(status)))
    with pytest.raises(error):
        provider.daily_bars("AAA", date(2026, 1, 1), date(2026, 1, 2))


def test_malformed_response_raises():
    bad = client(lambda r: httpx.Response(200, json=[{"date": "2026-07-07T00:00"}]))
    with pytest.raises(FeedError):
        TiingoProvider("x", bad).daily_bars("AAA", date(2026, 1, 1), date(2026, 1, 2))


def test_sec_parses_listed_forms_only():
    payload = {
        "filings": {
            "recent": {
                "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
                "form": ["10-K", "4"],
                "filingDate": ["2026-01-30", "2026-01-31"],
                "reportDate": ["2025-12-31", ""],
                "acceptanceDateTime": ["2026-01-30T16:30:00.000Z", ""],
                "primaryDocument": ["a.htm", "b.xml"],
            }
        }
    }
    rows, _ = SecProvider("a@b.test", client(lambda r: httpx.Response(200, json=payload))).filings(
        320193
    )
    assert [row.form for row in rows] == ["10-K"]
    assert rows[0].document_url.endswith("/320193/000032019326000001/a.htm")


def long_bars(count):
    days = market.sessions_between(date(2025, 1, 2), date(2026, 7, 7))[-count:]
    return [bar(day, close=100.0 + i * 0.1) for i, day in enumerate(days)]


def test_chart_shows_candles_and_leaves_warm_up_blank(stocks):
    run_prices(stocks, FixturePrices({"AAA": long_bars(260)}), START, 45, NOW)
    result = queries.chart(stocks, "AAA", "daily")
    assert len(result["candles"]) == 260
    assert result["candles"][0]["sma20"] is None
    assert result["candles"][-1]["sma200"] is not None
    assert result["stale"] is True  # The fixture ends in the past, relative to the real clock.


def test_stale_data_blocks_signals(stocks):
    run_prices(stocks, FixturePrices({"AAA": long_bars(260)}), START, 45, NOW)
    result = queries.chart(stocks, "AAA", "daily")
    assert result["signals_blocked"] is True
    assert result["signals"] == []


def test_chart_with_no_bars_is_empty_not_filled(stocks):
    result = queries.chart(stocks, "BBB", "daily")
    assert result["candles"] == []
    assert result["latest_bar"] is None


def test_hourly_limit_mid_run_is_not_a_failure(stocks):
    provider = FixturePrices(
        {"AAA": [bar(d) for d in SESSIONS]}, {"BBB": RateLimited("Tiingo BBB: rate limit")}
    )
    assert run_prices(stocks, provider, START, 45, NOW) == "ok"
    assert "next run continues" in last_run(stocks, "prices").message


def test_missing_record_raises_not_available():
    from stockintel.providers.base import NotAvailable

    provider = SecProvider("a@b.test", client(lambda r: httpx.Response(404)))
    with pytest.raises(NotAvailable):
        provider.company_facts(1)


def test_owned_stocks_get_prices_first(stocks):
    with stocks.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO positions (security_id, shares, buy_price)
                   SELECT id, 1, 1 FROM securities WHERE ticker = 'BBB'"""
            )
        )
    provider = FixturePrices()
    run_prices(stocks, provider, START, 1, NOW)
    assert [call[0] for call in provider.calls] == ["BBB"]
