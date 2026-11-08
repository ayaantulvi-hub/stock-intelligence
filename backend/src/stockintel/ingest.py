"""Scheduled ingestion. Run: python -m stockintel.ingest universe|prices|filings|economic"""

import argparse
import logging
import os
import re
import sys
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from stockintel import localcache, news_judge, news_watch
from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.market import PUBLISH_DELAY, latest_expected_session, session_close
from stockintel.providers import news
from stockintel.providers.base import (
    EconomicProvider,
    FeedError,
    FilingsProvider,
    NotAvailable,
    PriceBar,
    PriceProvider,
    Provenance,
    RateLimited,
)
from stockintel.providers.fed import FedProvider
from stockintel.providers.federal_register import FederalRegisterProvider
from stockintel.providers.finra import FinraProvider
from stockintel.providers.fred import FredProvider
from stockintel.providers.groq import GroqProvider
from stockintel.providers.house import HouseProvider
from stockintel.providers.news import NewsProvider
from stockintel.providers.sec import SecProvider
from stockintel.providers.tiingo import TiingoProvider
from stockintel.validation import bar_problem, find_issues
from stockintel.worker import record_heartbeat

log = logging.getLogger("stockintel.ingest")

EXCHANGES = {"NYSE", "Nasdaq"}
KNOWN_FILINGS_WINDOW = timedelta(days=90)
INSIDER_LOOKBACK = timedelta(days=730)
ECONOMIC_SERIES = (
    "DGS2",
    "DGS10",
    "T10Y3M",
    "DFF",
    "USEPUINDXD",
    "SP500",
    "NASDAQCOM",
    "DJIA",
    "FEDFUNDS",
    "CPIAUCSL",
    "UNRATE",
    "GDPC1",
    "VIXCLS",
    "BAA10Y",
    "DCOILWTICO",
    "T10YIE",
    "ICSA",
    "DTWEXBGS",
)
FIRST_FED_YEAR = 2009
FIRST_FLOAT_YEAR = 2009
# FRED rejects full version history for these daily series.
CURRENT_VALUES_ONLY = {
    "DGS2",
    "DGS10",
    "T10Y3M",
    "DFF",
    "USEPUINDXD",
    "SP500",
    "NASDAQCOM",
    "DJIA",
    "VIXCLS",
    "BAA10Y",
    "DCOILWTICO",
    "T10YIE",
    "ICSA",
    "DTWEXBGS",
}
FIRST_POLICY_YEAR = 2010
MARKET_FUNDS = ("SPY", "QQQ", "DIA")
FUND_YEARS = 12
# Well-known investors' SEC numbers. Each name comes back from the SEC and is stored.
FUNDS = (1067983, 1037389, 1350694, 1336528, 1649339, 1656456, 1061768, 1040273)
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
        self.paused = False
        with engine.begin() as conn:
            self.id = conn.execute(
                text("INSERT INTO feed_runs (feed) VALUES (:feed) RETURNING id"), {"feed": feed}
            ).scalar()

    def finish(self, fatal: str | None = None) -> str:
        if fatal:
            self.errors.insert(0, fatal)
        if fatal or (self.attempted and not self.ok):
            status = "error"
        elif self.paused and len(self.errors) == 1:
            # Reaching the hourly limit mid-run is expected. The next run carries on.
            status = "ok"
            self.errors = [
                f"Hourly limit reached after {self.ok} stocks. The next run continues."
                if self.feed == "prices"
                else "Hourly limit reached. The next run tries again."
            ]
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
                   ORDER BY EXISTS (SELECT 1 FROM positions h WHERE h.security_id = s.id) DESC,
                     s.last_price_fetch_at NULLS FIRST, s.universe_rank LIMIT :limit"""
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
            run.paused = True
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
            # Older filings are stored already, and re-reading them all costs database transfer.
            since = now.date() - KNOWN_FILINGS_WINDOW
            known = set(
                conn.execute(
                    text(
                        """SELECT accession_number FROM filings
                           WHERE security_id = :id AND filing_date >= :since"""
                    ),
                    {"id": security.id, "since": since},
                ).scalars()
            )
            filings = [filing for filing in filings if filing.filing_date >= since]
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
            known_events = set(
                conn.execute(
                    text(
                        """SELECT accession_number FROM filing_events
                           WHERE security_id = :id AND filing_date >= :since"""
                    ),
                    {"id": security.id, "since": since},
                ).scalars()
            )
            events = [
                filing
                for filing in filings
                if filing.items
                and filing.form in ("8-K", "8-K/A")
                and filing.accession_number not in known_events
            ]
            if events:
                event_fetch = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO filing_events (security_id, fetch_id, accession_number,
                             form, filing_date, items, document_url)
                           VALUES (:security_id, :fetch_id, :accession_number, :form,
                             :filing_date, :items, :document_url)"""
                    ),
                    [
                        {
                            "security_id": security.id,
                            "fetch_id": event_fetch,
                            "accession_number": filing.accession_number,
                            "form": filing.form,
                            "filing_date": filing.filing_date,
                            "items": filing.items,
                            "document_url": filing.document_url,
                        }
                        for filing in events
                    ],
                )
            conn.execute(
                text(
                    """UPDATE securities SET last_filing_fetch_at = :now,
                         sic = COALESCE(:sic, sic) WHERE id = :id"""
                ),
                {
                    "now": now,
                    "id": security.id,
                    "sic": getattr(provider, "sic", {}).get(security.cik),
                },
            )
        run.added += len(new)
        run.ok += 1
    return run.finish()


def run_facts(engine: Engine, provider) -> str:
    run = Run(engine, "facts")
    with engine.connect() as conn:
        securities = conn.execute(
            text("SELECT id, ticker, cik FROM securities ORDER BY universe_rank")
        ).all()
    stored = localcache.load(engine, "company_facts")
    known_keys: dict = {}
    for security_id, group in stored.groupby("security_id"):
        known_keys[security_id] = {
            (tag, None if pd.isna(start) else start, end, accession)
            for tag, start, end, accession in zip(
                group["tag"],
                group["period_start"],
                group["period_end"],
                group["accession_number"],
                strict=True,
            )
        }
    for security in securities:
        run.attempted += 1
        try:
            facts, provenance = provider.company_facts(security.cik)
        except NotAvailable:
            # Some companies publish no structured figures. They show as Not verified.
            run.ok += 1
            continue
        except RateLimited as exc:
            run.errors.append(str(exc))
            break
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            known = known_keys.get(security.id, set())
            new, seen = [], set()
            for fact in facts:
                key = (fact.tag, fact.period_start, fact.period_end, fact.accession_number)
                if key not in known and key not in seen:
                    seen.add(key)
                    new.append(fact)
            if new:
                fetch_id = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO company_facts (security_id, fetch_id, tag, unit,
                             period_start, period_end, value, accession_number, fiscal_period,
                             form, filed, document_url)
                           VALUES (:security_id, :fetch_id, :tag, :unit, :period_start,
                             :period_end, :value, :accession_number, :fiscal_period, :form,
                             :filed, :document_url)"""
                    ),
                    [
                        {**fact.__dict__, "security_id": security.id, "fetch_id": fetch_id}
                        for fact in new
                    ],
                )
        run.added += len(new)
        run.ok += 1
    return run.finish()


def run_insiders(engine: Engine, provider, now: datetime, limit: int) -> str:
    """Read Form 4 documents, newest companies' backlog first, up to `limit` a run."""
    run = Run(engine, "insiders")
    since = now.date() - INSIDER_LOOKBACK
    with engine.connect() as conn:
        securities = conn.execute(
            text("SELECT id, ticker, cik FROM securities ORDER BY universe_rank")
        ).all()
        read = set(conn.execute(text("SELECT accession_number FROM insider_documents")).scalars())
    for security in securities:
        if run.attempted >= limit:
            break
        try:
            documents = provider.insider_documents(security.cik, since)
        except RateLimited as exc:
            run.errors.append(str(exc))
            break
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        for document in documents:
            if document.accession_number in read or run.attempted >= limit:
                continue
            run.attempted += 1
            try:
                trades, provenance = provider.insider_trades(document.url)
            except RateLimited as exc:
                run.errors.append(str(exc))
                return run.finish()
            except FeedError as exc:
                run.errors.append(str(exc))
                continue
            with engine.begin() as conn:
                if trades:
                    fetch_id = add_fetch(conn, provenance)
                    conn.execute(
                        text(
                            """INSERT INTO insider_transactions (security_id, fetch_id,
                                 accession_number, line, owner, title, transaction_date, filed,
                                 code, shares, price, planned_sale, document_url)
                               VALUES (:security_id, :fetch_id, :accession, :line, :owner, :title,
                                 :transaction_date, :filed, :code, :shares, :price, :planned_sale,
                                 :url)"""
                        ),
                        [
                            {
                                **trade.__dict__,
                                "security_id": security.id,
                                "fetch_id": fetch_id,
                                "accession": document.accession_number,
                                "filed": document.filed,
                                "url": document.url,
                            }
                            for trade in trades
                        ],
                    )
                conn.execute(
                    text("INSERT INTO insider_documents (accession_number) VALUES (:a)"),
                    {"a": document.accession_number},
                )
            read.add(document.accession_number)
            run.added += len(trades)
            run.ok += 1
    return run.finish()


def run_history(engine: Engine, provider, now: datetime) -> str:
    """Store each year's company sizes, so stock lists can be rebuilt as they stood."""
    run = Run(engine, "history")
    with engine.connect() as conn:
        known = set(conn.execute(text("SELECT DISTINCT year FROM historic_float")).scalars())
    for year in range(FIRST_FLOAT_YEAR, now.year):
        if year in known:
            continue
        run.attempted += 1
        try:
            rows, provenance = provider.public_floats(year)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        best: dict[int, float] = {}
        for cik, value in rows:
            best[cik] = max(value, best.get(cik, 0.0))
        ordered = sorted(best.items(), key=lambda item: item[1], reverse=True)
        with engine.begin() as conn:
            fetch_id = add_fetch(conn, provenance)
            conn.execute(
                text(
                    """INSERT INTO historic_float (year, cik, public_float, size_rank, fetch_id)
                       VALUES (:year, :cik, :value, :rank, :fetch_id)"""
                ),
                [
                    {"year": year, "cik": cik, "value": value, "rank": rank, "fetch_id": fetch_id}
                    for rank, (cik, value) in enumerate(ordered, 1)
                ],
            )
        run.added += len(ordered)
        run.ok += 1
    return run.finish()


def run_fed(engine: Engine, provider) -> str:
    run = Run(engine, "fed")
    run.attempted = 1
    try:
        days, provenance = provider.meetings(FIRST_FED_YEAR)
    except FeedError as exc:
        return run.finish(str(exc))
    with engine.begin() as conn:
        known = set(conn.execute(text("SELECT decision_date FROM fed_meetings")).scalars())
        new = [day for day in days if day not in known]
        if new:
            fetch_id = add_fetch(conn, provenance)
            conn.execute(
                text("INSERT INTO fed_meetings (decision_date, fetch_id) VALUES (:day, :fetch_id)"),
                [{"day": day, "fetch_id": fetch_id} for day in new],
            )
    run.ok, run.added = 1, len(new)
    return run.finish()


def run_policy(engine: Engine, provider, now: datetime) -> str:
    """Store executive orders and proclamations, a year at a time on the first load."""
    run = Run(engine, "policy")
    with engine.connect() as conn:
        known = set(conn.execute(text("SELECT document_number FROM policy_documents")).scalars())
        newest = conn.execute(text("SELECT max(published) FROM policy_documents")).scalar()
    first = (newest - timedelta(days=30)).year if newest else FIRST_POLICY_YEAR
    for year in range(first, now.year + 1):
        run.attempted += 1
        try:
            documents, provenance = provider.documents(
                date(year, 1, 1), min(date(year, 12, 31), now.date())
            )
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        new = [item for item in documents if item.document_number not in known]
        known.update(item.document_number for item in new)
        if new:
            with engine.begin() as conn:
                fetch_id = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO policy_documents (document_number, fetch_id, kind, title,
                             published, topic, url)
                           VALUES (:document_number, :fetch_id, :kind, :title, :published, :topic,
                             :url)"""
                    ),
                    [{**item.__dict__, "fetch_id": fetch_id} for item in new],
                )
            run.added += len(new)
        run.ok += 1
    return run.finish()


def run_news(engine: Engine, provider, now: datetime) -> str:
    """Store new headlines under their topics and any company they name."""
    run = Run(engine, "news")
    with engine.connect() as conn:
        companies = [
            (ticker, news.plain_name(name))
            for ticker, name in conn.execute(text("SELECT ticker, name FROM securities"))
        ]
    touched = set()
    feeds = [(source, url, "news") for source, url in news.FEEDS.items()]
    feeds += [(source, url, "announcement") for source, url in news.ANNOUNCEMENTS.items()]
    feeds += [(source, url, "official") for source, url in news.OFFICIAL.items()]
    for source, url, kind in feeds:
        run.attempted += 1
        try:
            headlines, provenance = provider.feed(source, url)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            fetch_id = add_fetch(conn, provenance)
            for item in headlines:
                subjects = [t for t, name in companies if news.matches_company(name, item.title)]
                if kind == "news":
                    subjects += news.topics_of(item.title) + news.industries_of(item.title)
                elif kind == "official":
                    subjects += ["Official announcements"]
                for subject in subjects:
                    run.added += conn.execute(
                        text(
                            """INSERT INTO news_articles (fetch_id, subject, url, title, domain,
                                 seen_at)
                               VALUES (:fetch_id, :subject, :url, :title, :domain, :seen_at)
                               ON CONFLICT (subject, url) DO NOTHING"""
                        ),
                        {**item.__dict__, "fetch_id": fetch_id, "subject": subject},
                    ).rowcount
                    touched.add(subject)
        run.ok += 1
    _store_tone(engine, touched, now.date())
    news_watch.record(engine, now.date())
    return run.finish()


def _store_tone(engine: Engine, subjects: set[str], today: date) -> None:
    """A daily average of the rough headline mood, kept so it can be tested later."""
    with engine.begin() as conn:
        for subject in subjects:
            titles = (
                conn.execute(
                    text(
                        """SELECT title FROM news_articles
                       WHERE subject = :s AND seen_at::date = :day"""
                    ),
                    {"s": subject, "day": today},
                )
                .scalars()
                .all()
            )
            if titles:
                conn.execute(
                    text(
                        """INSERT INTO news_tone (subject, day, tone)
                           VALUES (:s, :day, :tone)
                           ON CONFLICT (subject, day) DO UPDATE SET tone = EXCLUDED.tone"""
                    ),
                    {
                        "s": subject,
                        "day": today,
                        "tone": sum(news.headline_mood(t) for t in titles) / len(titles),
                    },
                )


def issuer_key(name: str) -> str:
    """A company's name in the plain form both SEC lists can be compared on."""
    plain = news.plain_name(name).upper().replace(".", "").replace(",", "")
    return re.sub(r"\s+(INC|CORP|CO|CL A|CL B|COM|NEW|DEL|HLDGS)$", "", plain).strip()


def run_funds(engine: Engine, provider, now: datetime) -> str:
    """Store what well-known funds report owning, one fund's new reports at a time."""
    run = Run(engine, "funds")
    since = date(now.year - FUND_YEARS, 1, 1)
    with engine.connect() as conn:
        companies = {
            issuer_key(name): security_id
            for security_id, name in conn.execute(text("SELECT id, name FROM securities"))
        }
        known = set(conn.execute(text("SELECT accession_number FROM fund_filings")).scalars())
    for cik in FUNDS:
        run.attempted += 1
        try:
            name, filings = provider.fund_filings(cik, since)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        failed = False
        for filing in filings:
            if filing["accession_number"] in known:
                continue
            try:
                rows, url, provenance = provider.fund_holdings(cik, filing["accession_number"])
            except NotAvailable:
                continue
            except FeedError as exc:
                run.errors.append(str(exc))
                failed = True
                continue
            matched: dict[int, float] = {}
            for row in rows:
                security_id = companies.get(issuer_key(row["issuer"]))
                if security_id is not None:
                    matched[security_id] = matched.get(security_id, 0.0) + row["shares"]
            with engine.begin() as conn:
                fetch_id = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO fund_filings (accession_number, fund_cik, fund_name, period,
                             filed)
                           VALUES (:accession_number, :cik, :name, :period, :filed)"""
                    ),
                    {**filing, "cik": cik, "name": name},
                )
                for security_id, shares in matched.items():
                    conn.execute(
                        text(
                            """INSERT INTO fund_holdings (accession_number, fetch_id, security_id,
                                 fund_cik, period, filed, shares, document_url)
                               VALUES (:accession, :fetch_id, :security_id, :cik, :period, :filed,
                                 :shares, :url)"""
                        ),
                        {
                            "accession": filing["accession_number"],
                            "fetch_id": fetch_id,
                            "security_id": security_id,
                            "cik": cik,
                            "period": filing["period"],
                            "filed": filing["filed"],
                            "shares": shares,
                            "url": url,
                        },
                    )
                run.added += len(matched)
        if not failed:
            run.ok += 1
    return run.finish()


def run_judge(engine: Engine, now: datetime) -> str:
    """Have the AI read new headlines. A failure leaves decisions on the word-count rule."""
    run = Run(engine, "judge")
    run.attempted = 1
    provider = GroqProvider(os.environ.get("GROQ_API_KEY", ""))
    run.added, problem = news_judge.run(engine, provider, now)
    if problem:
        return run.finish(problem)
    run.ok = 1
    return run.finish()


def run_markets(engine: Engine, provider) -> str:
    """Store the latest price of each fund that tracks a main US index."""
    run = Run(engine, "markets")
    run.attempted = 1
    try:
        quotes, provenance = provider.quotes(MARKET_FUNDS)
    except RateLimited as exc:
        # Two runs in one hour can share the limit. The last stored prices still show.
        run.attempted, run.paused = 0, True
        run.errors.append(str(exc))
        return run.finish()
    except FeedError as exc:
        return run.finish(str(exc))
    with engine.begin() as conn:
        fetch_id = add_fetch(conn, provenance)
        for quote in quotes:
            run.added += conn.execute(
                text(
                    """INSERT INTO market_quotes (fetch_id, ticker, quoted_at, price,
                         previous_close)
                       VALUES (:fetch_id, :ticker, :quoted_at, :price, :previous_close)
                       ON CONFLICT (ticker, quoted_at) DO NOTHING"""
                ),
                {**quote.__dict__, "fetch_id": fetch_id},
            ).rowcount
    run.ok = 1
    return run.finish()


def run_economic(engine: Engine, provider: EconomicProvider) -> str:
    run = Run(engine, "economic")
    for series_id in ECONOMIC_SERIES:
        run.attempted += 1
        try:
            all_versions = series_id not in CURRENT_VALUES_ONLY
            observations, provenance = provider.observations(
                series_id, ECONOMIC_START, all_versions
            )
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            if not all_versions:
                current = dict(
                    conn.execute(
                        text(
                            """SELECT DISTINCT ON (observation_date) observation_date, value
                               FROM economic_observations WHERE series_id = :id
                               ORDER BY observation_date, realtime_start DESC"""
                        ),
                        {"id": series_id},
                    ).all()
                )
                observations = [
                    item
                    for item in observations
                    if item.observation_date not in current
                    or current[item.observation_date] != item.value
                ]
            if not observations:
                run.ok += 1
                continue
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


RELEASES = {"Inflation figures (CPI)": "CPIAUCSL", "Jobs report": "PAYEMS"}
RELEASES_FROM = date(2015, 1, 1)


def run_releases(engine: Engine, provider) -> str:
    """Past and scheduled dates of the market-moving economic releases."""
    run = Run(engine, "releases")
    for name, series in RELEASES.items():
        run.attempted += 1
        try:
            days, provenance = provider.release_dates(series, RELEASES_FROM)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            fetch_id = add_fetch(conn, provenance)
            added = conn.execute(
                text(
                    """INSERT INTO economic_releases (name, release_date, fetch_id)
                       VALUES (:name, :day, :fetch_id) ON CONFLICT DO NOTHING"""
                ),
                [{"name": name, "day": day, "fetch_id": fetch_id} for day in days],
            ).rowcount
        run.ok += 1
        run.added += max(added, 0)
    return run.finish()


SHORT_LOOKBACK = timedelta(days=60)


def run_short_interest(engine: Engine, provider, now: datetime) -> str:
    """The latest short interest for every tracked stock, from FINRA."""
    run = Run(engine, "short interest")
    with engine.connect() as conn:
        stocks = {
            row.ticker.replace("-", "."): row.id
            for row in conn.execute(text("SELECT id, ticker FROM securities"))
        }
    run.attempted = len(stocks)
    try:
        rows, provenance = provider.short_interest(
            sorted(stocks), (now - SHORT_LOOKBACK).date(), now.date()
        )
    except FeedError as exc:
        return run.finish(str(exc))
    found = [r for r in rows if r.symbol in stocks]
    with engine.begin() as conn:
        fetch_id = add_fetch(conn, provenance)
        for row in found:
            run.added += conn.execute(
                text(
                    """INSERT INTO short_interest (security_id, settlement_date, short_shares,
                         previous_short_shares, avg_daily_volume, days_to_cover, fetch_id)
                       VALUES (:id, :day, :short, :previous, :volume, :cover, :fetch_id)
                       ON CONFLICT DO NOTHING"""
                ),
                {
                    "id": stocks[row.symbol],
                    "day": row.settlement_date,
                    "short": row.short_shares,
                    "previous": row.previous_short_shares,
                    "volume": row.avg_daily_volume,
                    "cover": row.days_to_cover,
                    "fetch_id": fetch_id,
                },
            ).rowcount
    run.ok = len({r.symbol for r in found})
    return run.finish()


CONGRESS_FIRST_DAYS = 120


def run_congress(engine: Engine, provider, now: datetime, limit: int) -> str:
    """New House trade reports, newest first. The first run reads the last 120 days only."""
    run = Run(engine, "congress")
    reports = []
    for year in (now.year - 1, now.year):
        try:
            found, _ = provider.reports(year)
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        reports += found
    if not reports:
        return run.finish()
    with engine.connect() as conn:
        seen = set(conn.execute(text("SELECT doc_id FROM congress_reports")).scalars())
    cutoff = (now - timedelta(days=CONGRESS_FIRST_DAYS)).date()
    todo = sorted(
        (r for r in reports if r.doc_id not in seen and r.filed and r.filed >= cutoff),
        key=lambda r: r.filed,
        reverse=True,
    )[:limit]
    for report in todo:
        run.attempted += 1
        try:
            trades = provider.trades(report)
            note, ok = None, True
        except FeedError as exc:
            trades, note, ok = [], str(exc), False
            run.errors.append(f"{report.doc_id}: {exc}")
        with engine.begin() as conn:
            fetch_id = add_fetch(
                conn, Provenance("House Clerk", report.url, datetime.now(UTC), "end_of_day")
            )
            for trade in trades:
                run.added += conn.execute(
                    text(
                        """INSERT INTO congress_trades (doc_id, member, owner, ticker, asset,
                             action, trade_date, filed_date, amount, days_to_file, url, fetch_id)
                           VALUES (:doc, :member, :owner, :ticker, :asset, :action, :trade_date,
                             :filed, :amount, :days, :url, :fetch_id)
                           ON CONFLICT DO NOTHING"""
                    ),
                    {
                        "doc": report.doc_id,
                        "member": report.member,
                        "owner": trade["owner"],
                        "ticker": trade["ticker"],
                        "asset": trade["asset"],
                        "action": trade["action"],
                        "trade_date": trade["trade_date"],
                        "filed": report.filed,
                        "amount": trade["amount"],
                        "days": trade["days_to_file"],
                        "url": report.url,
                        "fetch_id": fetch_id,
                    },
                ).rowcount
            conn.execute(
                text(
                    """INSERT INTO congress_reports (doc_id, member, filed_date, read_ok, note)
                       VALUES (:doc, :member, :filed, :ok, :note) ON CONFLICT DO NOTHING"""
                ),
                {
                    "doc": report.doc_id,
                    "member": report.member,
                    "filed": report.filed,
                    "ok": ok,
                    "note": note,
                },
            )
        if ok:
            run.ok += 1
    return run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "feed",
        choices=[
            "universe",
            "prices",
            "filings",
            "economic",
            "facts",
            "insiders",
            "history",
            "policy",
            "news",
            "markets",
            "funds",
            "judge",
            "fed",
            "releases",
            "short",
            "congress",
        ],
    )
    parser.add_argument("--limit", type=int, default=45, help="stocks or documents per run")
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
        elif args.feed == "history":
            status = run_history(engine, SecProvider(settings.sec_contact_email), now)
        elif args.feed == "fed":
            status = run_fed(engine, FedProvider())
        elif args.feed == "news":
            status = run_news(engine, NewsProvider(), now)
        elif args.feed == "judge":
            status = run_judge(engine, now)
        elif args.feed == "funds":
            status = run_funds(engine, SecProvider(settings.sec_contact_email), now)
        elif args.feed == "markets":
            status = run_markets(engine, TiingoProvider(settings.tiingo_api_token))
        elif args.feed == "policy":
            status = run_policy(engine, FederalRegisterProvider(), now)
        elif args.feed == "facts":
            status = run_facts(engine, SecProvider(settings.sec_contact_email))
        elif args.feed == "insiders":
            status = run_insiders(engine, SecProvider(settings.sec_contact_email), now, args.limit)
        elif args.feed == "releases":
            status = run_releases(engine, FredProvider(settings.fred_api_key))
        elif args.feed == "short":
            status = run_short_interest(engine, FinraProvider(), now)
        elif args.feed == "congress":
            status = run_congress(engine, HouseProvider(), now, args.limit)
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
