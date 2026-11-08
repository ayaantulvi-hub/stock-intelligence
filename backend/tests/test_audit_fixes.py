"""Release dates, short interest, Congress trades, source cross-checks and override tests.
Every value here is a TEST FIXTURE."""

from datetime import UTC, date, datetime

import httpx
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel import conflicts, day_trading, ingest, overrides
from stockintel.providers.base import FeedError, Provenance
from stockintel.providers.finra import FinraProvider
from stockintel.providers.fred import FredProvider
from stockintel.providers.house import Report

NOW = datetime(2026, 11, 9, 12, tzinfo=UTC)


def add_stock(conn, ticker, rank, sic=None):
    return conn.execute(
        text(
            """INSERT INTO securities (ticker, cik, name, exchange, universe_rank, sic)
               VALUES (:t, :c, :t, 'NYSE', :r, :sic) RETURNING id"""
        ),
        {"t": ticker, "c": str(rank), "r": rank, "sic": sic},
    ).scalar()


def scalar(engine, query, **params):
    with engine.connect() as conn:
        return conn.execute(text(query), params).scalar()


def test_release_dates_are_looked_up_from_the_series():
    seen = []

    def answer(request):
        seen.append(request.url)
        if "series/release" in str(request.url):
            return httpx.Response(200, json={"releases": [{"id": 10}]})
        return httpx.Response(
            200, json={"release_dates": [{"date": "2026-11-13"}, {"date": "2026-10-15"}]}
        )

    fred = FredProvider("key", httpx.Client(transport=httpx.MockTransport(answer)))
    days, provenance = fred.release_dates("CPIAUCSL", date(2015, 1, 1))
    assert days == [date(2026, 10, 15), date(2026, 11, 13)]
    assert seen[1].params["release_id"] == "10"
    assert seen[1].params["include_release_dates_with_no_data"] == "true"
    assert "key" not in provenance.source_url


class FixtureFred:
    def release_dates(self, series, start):
        if series == "PAYEMS":
            raise FeedError("FRED release of PAYEMS: HTTP 500")
        return [date(2026, 11, 13)], Provenance("FRED", "https://fixture.test", NOW, "end_of_day")


def test_one_failed_release_is_reported_and_the_other_kept(engine):
    assert ingest.run_releases(engine, FixtureFred()) == "partial"
    assert scalar(engine, "SELECT name FROM economic_releases") == "Inflation figures (CPI)"


def test_finra_reads_pages_and_matches_dotted_tickers(engine):
    with engine.begin() as conn:
        add_stock(conn, "BRK-B", 1)
    record = {
        "symbolCode": "BRK.B",
        "settlementDate": "2026-10-15",
        "currentShortPositionQuantity": 1000,
        "previousShortPositionQuantity": 800,
        "averageDailyVolumeQuantity": 500,
        "daysToCoverQuantity": 2.0,
    }
    bodies = []

    def answer(request):
        bodies.append(request.content)
        return httpx.Response(200, json=[record, {**record, "symbolCode": "ZZZZ"}])

    finra = FinraProvider(httpx.Client(transport=httpx.MockTransport(answer)))
    assert ingest.run_short_interest(engine, finra, NOW) == "ok"
    assert b"BRK.B" in bodies[0] and b"settlementDate" in bodies[0]
    assert scalar(engine, "SELECT days_to_cover FROM short_interest") == 2.0


def test_finra_error_is_an_error():
    finra = FinraProvider(
        httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    )
    with pytest.raises(FeedError, match="HTTP 500"):
        finra.short_interest(["AAPL"], date(2026, 10, 1), date(2026, 11, 1))


class FixtureHouse:
    def __init__(self):
        self.read = []

    def reports(self, year):
        if year == 2025:
            return [], Provenance("House Clerk", "https://fixture.test", NOW, "end_of_day")
        return [
            Report("1", "Jane Doe", date(2026, 11, 1), 2026, "https://fixture.test/1.pdf"),
            Report("2", "John Roe", date(2026, 10, 30), 2026, "https://fixture.test/2.pdf"),
            Report("3", "Old Filer", date(2026, 1, 2), 2026, "https://fixture.test/3.pdf"),
        ], Provenance("House Clerk", "https://fixture.test", NOW, "end_of_day")

    def trades(self, report):
        self.read.append(report.doc_id)
        if report.doc_id == "2":
            raise FeedError("House Clerk: the report PDF couldn't be read")
        return [
            {
                "owner": "Spouse",
                "asset": "Apple Inc (AAPL) [ST]",
                "ticker": "AAPL",
                "action": "Buy",
                "trade_date": date(2026, 10, 20),
                "amount": "$1,001 - $15,000",
                "days_to_file": 12,
            }
        ]


def test_congress_reads_new_reports_once_and_records_failures(engine):
    house = FixtureHouse()
    assert ingest.run_congress(engine, house, NOW, 10) == "partial"
    assert house.read == ["1", "2"]  # The January report is older than the first-run window.
    assert scalar(engine, "SELECT ticker FROM congress_trades") == "AAPL"
    assert scalar(engine, "SELECT count(*) FROM congress_reports WHERE NOT read_ok") == 1
    house.read.clear()
    ingest.run_congress(engine, house, NOW, 10)
    assert house.read == []


class FixtureAlpaca:
    def minute_bars(self, symbols, start, end, timeframe="1Min", adjustment="split"):
        times = pd.to_datetime(["2026-11-05", "2026-11-06"]).tz_localize("America/New_York")
        data = {
            "AAA": [100.0, 100.2],
            "BBB": [50.0, 55.0],
            "SPY": [600.0, 606.0],
            "DIA": [450.0, 450.0],
        }
        frames = {
            s: pd.DataFrame(
                {"time": times, "open": c, "high": c, "low": c, "close": c, "volume": 1.0}
            )
            for s, c in data.items()
            if s in symbols
        }
        return frames, Provenance("Alpaca (IEX)", "https://fixture.test", NOW, "live")


def test_cross_check_flags_disagreements_with_both_values(engine):
    with engine.begin() as conn:
        for rank, (ticker, close) in enumerate((("AAA", 100.1), ("BBB", 50.0)), 1):
            sid = add_stock(conn, ticker, rank)
            fetch = conn.execute(
                text(
                    """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
                   WHERE name = 'Tiingo' RETURNING id"""
                )
            ).scalar()
            conn.execute(
                text(
                    """INSERT INTO price_bars (fetch_id, security_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (:f, :s, '2026-11-06', '2026-11-06', :c, :c, :c, :c, 1, 0, 1)"""
                ),
                {"f": fetch, "s": sid, "c": close},
            )
            fred = conn.execute(
                text(
                    """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
                   WHERE name = 'FRED' RETURNING id"""
                )
            ).scalar()
        for series, values in {"SP500": (6000.0, 6060.0), "DJIA": (45000.0, 45900.0)}.items():
            for day, value in zip(("2026-11-05", "2026-11-06"), values):
                conn.execute(
                    text(
                        """INSERT INTO economic_observations (fetch_id, series_id, observation_date,
                         realtime_start, value) VALUES (:f, :s, :d, :d, :v)"""
                    ),
                    {"f": fred, "s": series, "d": day, "v": value},
                )
    result = conflicts.run(engine, FixtureAlpaca(), datetime(2026, 11, 8, tzinfo=UTC))
    with engine.connect() as conn:
        found = {
            r.ticker: r.detail
            for r in conn.execute(
                text("SELECT ticker, detail FROM validation_issues WHERE kind = 'conflict'")
            )
        }
    assert set(found) == {"BBB", "DIA"}  # AAA is 0.1% apart; SPY moved as the S&P did.
    assert "Tiingo 50.00" in found["BBB"] and "Alpaca (IEX) 55.00" in found["BBB"]
    assert "+2.00% (FRED)" in found["DIA"]
    assert result["flagged"] == 2


def test_override_comparison_needs_enough_cases():
    assert (
        overrides.compare(np.array([0.01] * 5), np.array([0.02] * 50))["verdict"]
        == "Not enough history yet"
    )
    rng = np.random.default_rng(1)
    worse = overrides.compare(rng.normal(-0.05, 0.02, 40), rng.normal(0.01, 0.02, 400))
    assert worse["verdict"] == "Helped: blocked stocks did worse"
    same = overrides.compare(np.tile([-0.01, 0.01], 20), np.tile([-0.01, 0.01], 200))
    assert same["verdict"] == "No difference shown"


def test_override_run_with_no_history_says_so(engine):
    results = overrides.run(engine)
    assert results["Expert checks"]["verdict"] == "Not enough history yet"
    assert {row["rule"] for row in overrides.latest(engine)} == {"Expert checks", "News warnings"}


def test_test_rows_are_labelled_by_release_and_results_days():
    rows = [
        {"symbol": "AAA", "entered": pd.Timestamp("2026-11-13 15:00", tz="UTC")},
        {"symbol": "AAA", "entered": pd.Timestamp("2026-11-16 15:00", tz="UTC")},
    ]
    events = {date(2026, 11, 13): ["Inflation figures (CPI)"]}
    labelled = day_trading.label_days(rows, events, {"AAA": {date(2026, 11, 16)}})
    assert [r["event_day"] for r in labelled] == ["Release or Fed day", "Ordinary day"]
    assert [r["results_day"] for r in labelled] == ["No results", "Results day"]


def test_setups_get_cautions_on_release_days(engine):
    result = {"stocks": [{"setups": [{"ticker": "SPY"}]}], "orb": {"setups": [{"ticker": "AAA"}]}}
    day_trading.add_cautions(engine, result, date(2026, 11, 13), ["Inflation figures (CPI)"])
    assert result["stocks"][0]["setups"][0]["cautions"][0].startswith(
        "Inflation figures (CPI) today"
    )
    assert result["orb"]["setups"][0]["cautions"]


def test_views_show_matched_trades_short_interest_and_checks(engine):
    from stockintel import extras

    house = FixtureHouse()
    with engine.begin() as conn:
        add_stock(conn, "AAPL", 1)
    ingest.run_congress(engine, house, datetime.now(UTC), 10)
    view = extras.congress(engine, days=3650)
    assert [t["ticker"] for t in view["trades"]] == ["AAPL"]
    assert view["reports_unread"] == 1
    assert extras.congress(engine, "MSFT", days=3650)["trades"] == []
    assert extras.short_interest(engine, "AAPL") is None
    assert extras.checks(engine)["conflicts"] == []
