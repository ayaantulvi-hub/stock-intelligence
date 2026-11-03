"""Scheduled ingestion. Run: python -m stockintel.ingest universe|prices|filings|economic"""

import argparse
import logging
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.market import PUBLISH_DELAY, latest_expected_session, session_close
from stockintel.providers.base import (
    EconomicProvider,
    FeedError,
    FilingsProvider,
    PriceBar,
    PriceProvider,
    Provenance,
    RateLimited,
)
from stockintel.providers.fred import FredProvider
from stockintel.providers.sec import SecProvider
from stockintel.providers.tiingo import TiingoProvider
from stockintel.validation import bar_problem, find_issues
from stockintel.worker import record_heartbeat

log = logging.getLogger("stockintel.ingest")

EXCHANGES = {"NYSE", "Nasdaq"}
ECONOMIC_SERIES = ("DGS2", "DGS10", "FEDFUNDS", "CPIAUCSL", "UNRATE", "GDPC1")
ECONOMIC_START = date(2005, 1, 1)
# Re-read recent days, because Tiingo publishes corrections through the evening.
CORRECTION_WINDOW = timedelta(days=5)
PRICE_FIELDS = ("open", "high", "low", "close", "volume", "div_cash", "split_factor")


class Run:
    """Records one feed run, including failures, in feed_runs."""

    def __init__(self, engine: Engine, feed: str):
        self.engine, self.feed = engine, feed
        self.attempted = self.ok = self.added = 0
        self.errors: list[str] = []
        with engine.begin() as conn:
            self.id = conn.execute(
                text("INSERT INTO feed_runs (feed) VALUES (:feed) RETURNING id"), {"feed": feed}
            ).scalar()

    def finish(self, fatal: str | None = None) -> str:
        if fatal:
            self.errors.insert(0, fatal)
        if fatal or (self.attempted and not self.ok):
            status = "error"
        elif self.errors:
            status = "partial"
        else:
            status = "ok"
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """UPDATE feed_runs SET finished_at = now(), status = :status,
                       items_attempted = :attempted, items_ok = :ok,
                       records_added = :added, message = :message WHERE id = :id"""
                ),
                {
                    "status": status,
                    "attempted": self.attempted,
                    "ok": self.ok,
                    "added": self.added,
                    "message": "; ".join(self.errors[:5]) or None,
                    "id": self.id,
                },
            )
        log.info("%s: %s, %s records added", self.feed, status, self.added)
        return status


def add_fetch(conn: Connection, provenance: Provenance) -> int:
    return conn.execute(
        text(
            """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
               SELECT id, :url, :retrieved, :status FROM data_sources WHERE name = :name
               RETURNING id"""
        ),
        {
            "url": provenance.source_url,
            "retrieved": provenance.retrieved_at,
            "status": provenance.data_status,
            "name": provenance.source_name,
        },
    ).scalar_one()


def add_issue(conn: Connection, feed: str, kind: str, ticker, day, detail: str) -> None:
    conn.execute(
        text(
            """INSERT INTO validation_issues (feed, kind, ticker, market_date, detail)
               VALUES (:feed, :kind, :ticker, :day, :detail)"""
        ),
        {"feed": feed, "kind": kind, "ticker": ticker, "day": day, "detail": detail},
    )


def run_universe(engine: Engine, provider: FilingsProvider, size: int) -> str:
    """Pick the stock list once. It stays fixed, because Tiingo's free plan caps symbols."""
    run = Run(engine, "universe")
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT count(*) FROM securities")).scalar()
    if existing:
        return run.finish()
    try:
        listings, _ = provider.listings()
    except FeedError as exc:
        return run.finish(str(exc))
    chosen, seen = [], set()
    # The SEC file is ordered largest first in practice. It does not promise this.
    for listing in listings:
        if listing.exchange in EXCHANGES and listing.cik not in seen:
            seen.add(listing.cik)
            chosen.append(listing)
        if len(chosen) == size:
            break
    if len(chosen) < size:
        return run.finish(f"SEC tickers: only {len(chosen)} listings found")
    with engine.begin() as conn:
        for rank, listing in enumerate(chosen, 1):
            conn.execute(
                text(
                    """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                       VALUES (:ticker, :cik, :name, :exchange, :rank)"""
                ),
                {**listing.__dict__, "rank": rank},
            )
    run.attempted = run.ok = run.added = len(chosen)
    return run.finish()


def _store_bars(conn: Connection, security_id: int, ticker: str, bars, provenance) -> int:
    """Add new and corrected bars. A correction is a new row, so the old value is kept."""
    latest = {
        row.market_date: tuple(getattr(row, field) for field in PRICE_FIELDS)
        for row in conn.execute(
            text(
                """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                          volume, div_cash, split_factor
                   FROM price_bars WHERE security_id = :id AND market_date >= :start
                   ORDER BY market_date, id DESC"""
            ),
            {"id": security_id, "start": min(bar.market_date for bar in bars)},
        )
    }
    good: list[PriceBar] = []
    for bar in bars:
        problem = bar_problem(bar)
        if problem:
            add_issue(conn, "prices", "invalid", ticker, bar.market_date, f"rejected: {problem}")
        else:
            good.append(bar)
    new = [
        bar
        for bar in good
        if latest.get(bar.market_date) != tuple(getattr(bar, field) for field in PRICE_FIELDS)
    ]
    if new:
        fetch_id = add_fetch(conn, provenance)
        conn.execute(
            text(
                """INSERT INTO price_bars (security_id, fetch_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (:security_id, :fetch_id, :market_date, :market_timestamp,
                     :open, :high, :low, :close, :volume, :div_cash, :split_factor)"""
            ),
            [
                {
                    **bar.__dict__,
                    "security_id": security_id,
                    "fetch_id": fetch_id,
                    "market_timestamp": session_close(bar.market_date),
                }
                for bar in new
            ],
        )
    for issue in find_issues(good):
        add_issue(conn, "prices", issue.kind, ticker, issue.market_date, issue.detail)
    return len(new)


def run_prices(
    engine: Engine, provider: PriceProvider, history_start: date, limit: int, now: datetime
) -> str:
    run = Run(engine, "prices")
    expected = latest_expected_session(now)
    due_before = session_close(expected) + PUBLISH_DELAY
    with engine.connect() as conn:
        due = conn.execute(
            text(
                """SELECT s.id, s.ticker, (SELECT max(market_date) FROM price_bars p
                                           WHERE p.security_id = s.id) AS last_bar
                   FROM securities s
                   WHERE s.last_price_fetch_at IS NULL OR s.last_price_fetch_at < :due
                   ORDER BY s.last_price_fetch_at NULLS FIRST, s.universe_rank LIMIT :limit"""
            ),
            {"due": due_before, "limit": limit},
        ).all()
    for security in due:
        run.attempted += 1
        start = security.last_bar - CORRECTION_WINDOW if security.last_bar else history_start
        try:
            bars, provenance = provider.daily_bars(security.ticker, start, expected)
        except RateLimited as exc:
            run.errors.append(str(exc))
            break  # Further requests would fail too, and may extend the block.
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            if bars:
                run.added += _store_bars(conn, security.id, security.ticker, bars, provenance)
            else:
                add_issue(
                    conn, "prices", "missing", security.ticker, None, "source returned no bars"
                )
            conn.execute(
                text("UPDATE securities SET last_price_fetch_at = :now WHERE id = :id"),
                {"now": now, "id": security.id},
            )
        run.ok += 1
    return run.finish()


def run_filings(engine: Engine, provider: FilingsProvider, now: datetime) -> str:
    run = Run(engine, "filings")
    with engine.connect() as conn:
        securities = conn.execute(
            text("SELECT id, ticker, cik FROM securities ORDER BY universe_rank")
        ).all()
    for security in securities:
        run.attempted += 1
        try:
            filings, provenance = provider.filings(security.cik)
        except RateLimited as exc:
            run.errors.append(str(exc))
            break
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            known = set(
                conn.execute(
                    text("SELECT accession_number FROM filings WHERE security_id = :id"),
                    {"id": security.id},
                ).scalars()
            )
            new = [filing for filing in filings if filing.accession_number not in known]
            if new:
                fetch_id = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO filings (security_id, fetch_id, accession_number, form,
                             filing_date, report_date, accepted_at, document_url)
                           VALUES (:security_id, :fetch_id, :accession_number, :form,
                             :filing_date, :report_date, :accepted_at, :document_url)"""
                    ),
                    [
                        {**filing.__dict__, "security_id": security.id, "fetch_id": fetch_id}
                        for filing in new
                    ],
                )
            conn.execute(
                text("UPDATE securities SET last_filing_fetch_at = :now WHERE id = :id"),
                {"now": now, "id": security.id},
            )
        run.added += len(new)
        run.ok += 1
    return run.finish()


def run_economic(engine: Engine, provider: EconomicProvider) -> str:
    run = Run(engine, "economic")
    for series_id in ECONOMIC_SERIES:
        run.attempted += 1
        try:
            observations, provenance = provider.observations(series_id, ECONOMIC_START)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            fetch_id = add_fetch(conn, provenance)
            result = conn.execute(
                text(
                    """INSERT INTO economic_observations
                         (series_id, fetch_id, observation_date, realtime_start, value)
                       SELECT :series_id, :fetch_id, :observation_date, :realtime_start, :value
                       WHERE NOT EXISTS (SELECT 1 FROM economic_observations
                         WHERE series_id = :series_id AND observation_date = :observation_date
                           AND realtime_start = :realtime_start)"""
                ),
                [
                    {**item.__dict__, "series_id": series_id, "fetch_id": fetch_id}
                    for item in observations
                ],
            )
            run.added += max(result.rowcount, 0)
        run.ok += 1
    return run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", choices=["universe", "prices", "filings", "economic"])
    parser.add_argument("--limit", type=int, default=45, help="stocks per price run")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = get_settings()
    engine = get_engine()
    now = datetime.now(UTC)
    try:
        if args.feed == "universe":
            status = run_universe(
                engine, SecProvider(settings.sec_contact_email), settings.universe_size
            )
        elif args.feed == "prices":
            status = run_prices(
                engine,
                TiingoProvider(settings.tiingo_api_token),
                date.fromisoformat(settings.price_history_start),
                args.limit,
                now,
            )
        elif args.feed == "filings":
            status = run_filings(engine, SecProvider(settings.sec_contact_email), now)
        else:
            status = run_economic(engine, FredProvider(settings.fred_api_key))
    except FeedError as exc:  # For example, a missing key.
        status = Run(engine, args.feed).finish(str(exc))
    record_heartbeat(engine)
    if status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
