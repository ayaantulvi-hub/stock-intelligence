"""Scheduled data collection for the quant lab.

Run: python -m stockintel.ingest universe|prices|alpaca-closes|history|economic
- universe: the largest US-listed companies, from SEC EDGAR.
- prices: daily bars from Tiingo, about 45 stocks an hour (its free limit).
- alpaca-closes: the latest close for every stock still missing it, from Alpaca.
- history: each company's yearly public float from SEC filings, to rebuild who was large.
- economic: the Fed funds rate from FRED, used as the risk-free rate.
"""

import argparse
import logging
import sys
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import Engine, text
from sqlalchemy.engine import Connection

from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.market import PUBLISH_DELAY, latest_expected_session, session_close
from stockintel.providers.alpaca import AlpacaProvider
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
from stockintel.providers.french import FrenchProvider
from stockintel.providers.sec import SecProvider
from stockintel.providers.tiingo import TiingoProvider
from stockintel.validation import bar_problem, find_issues
from stockintel.worker import record_heartbeat

log = logging.getLogger("stockintel.ingest")

EXCHANGES = {"NYSE", "Nasdaq"}
# Only the Fed funds rate is still used (as the risk-free rate in the quant lab).
ECONOMIC_SERIES = ("DFF",)
FIRST_FLOAT_YEAR = 2009
# FRED rejects full version history for these daily series.
CURRENT_VALUES_ONLY = {"DFF"}
ECONOMIC_START = date(2005, 1, 1)
# Re-read recent days, because Tiingo publishes corrections through the evening.
CORRECTION_WINDOW = timedelta(days=5)
PRICE_FIELDS = ("open", "high", "low", "close", "volume", "div_cash", "split_factor")
SPLIT_SUSPECT = 0.4  # A one-day move this big may be a split; leave that day to Tiingo.


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
        if self.errors:
            # Feed errors name sources and stocks, never holdings, so they're safe in public logs.
            log.info("%s problems: %s", self.feed, "; ".join(self.errors[:5]))
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


INDUSTRY_LIMIT = 50  # SEC lookups a run for stocks still missing an industry code.


def _fill_industries(engine: Engine, provider: FilingsProvider, run: "Run") -> None:
    """Add the SEC industry code for stocks that lack one. Pairs trading only pairs stocks in
    the same industry, so a stock without a code would silently drop out of it."""
    with engine.connect() as conn:
        missing = conn.execute(
            text(
                """SELECT id, ticker, cik FROM securities WHERE sic IS NULL AND cik IS NOT NULL
                   ORDER BY universe_rank LIMIT :limit"""
            ),
            {"limit": INDUSTRY_LIMIT},
        ).all()
    for row in missing:
        run.attempted += 1
        try:
            sic = provider.industry(row.cik)
        except FeedError as exc:
            run.errors.append(f"{row.ticker}: {exc}")
            continue
        run.ok += 1
        if sic is None:  # A fact about the company, not a failure. Coverage reports the count.
            continue
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE securities SET sic = :sic WHERE id = :id"), {"sic": sic, "id": row.id}
            )
        run.added += 1


def run_universe(engine: Engine, provider: FilingsProvider, size: int) -> str:
    """Pick the stock list once. It stays fixed, because Tiingo's free plan caps symbols.
    Each later run only fills in missing industry codes."""
    run = Run(engine, "universe")
    with engine.connect() as conn:
        existing = conn.execute(text("SELECT count(*) FROM securities")).scalar()
    if existing:
        _fill_industries(engine, provider, run)
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
    _fill_industries(engine, provider, run)
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


def run_market_history(engine: Engine, provider) -> str:
    """Daily factor returns from the French library: the US market since 1926 and the factors
    used by factor momentum. Only new days and changed values are stored, so a revision keeps
    the earlier value. One file failing doesn't stop the others."""
    from stockintel.providers.french import FILES

    run = Run(engine, "market history")
    with engine.connect() as conn:
        current = {
            (r.series, r.market_date): r.value
            for r in conn.execute(
                text(
                    """SELECT DISTINCT ON (series, market_date) series, market_date, value
                       FROM factor_returns ORDER BY series, market_date, id DESC"""
                )
            )
        }
    for name in FILES:
        run.attempted += 1
        try:
            rows, provenance = provider.daily(name)
        except FeedError as exc:
            run.errors.append(f"{name}: {exc}")
            continue
        new = [
            {"series": series, "day": day, "value": value}
            for day, values in rows
            for series, value in values.items()
            if current.get((series, day)) != value
        ]
        if new:
            with engine.begin() as conn:
                fetch_id = add_fetch(conn, provenance)
                conn.execute(
                    text(
                        """INSERT INTO factor_returns (fetch_id, series, market_date, value)
                           VALUES (:fetch_id, :series, :day, :value)"""
                    ),
                    [{**row, "fetch_id": fetch_id} for row in new],
                )
        run.ok += 1
        run.added += len(new)
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


def run_alpaca_closes(engine: Engine, provider, now: datetime) -> str:
    """Fill the latest session's close for every stock still missing it, from Alpaca's
    consolidated feed in a few requests. Tiingo, limited to about 45 stocks an hour, adds its own
    bar later with dividend and split details; readers use the newest bar for a day, and both are
    kept. A day that looks like a split is skipped and left to Tiingo."""
    run = Run(engine, "alpaca closes")
    day = latest_expected_session(now)
    query = """SELECT s.ticker, s.id, last.close AS previous FROM securities s
               JOIN LATERAL (SELECT market_date, close / split_factor AS close FROM price_bars
                 WHERE security_id = s.id ORDER BY market_date DESC, id DESC LIMIT 1) last ON true
               WHERE last.market_date < :day AND last.market_date >= :day - 10"""
    with engine.connect() as conn:
        missing = {r.ticker: r for r in conn.execute(text(query), {"day": day})}
    run.attempted = len(missing)
    if not missing:
        return run.finish()
    start = datetime.combine(day, time(0), tzinfo=UTC)
    names = {t.replace("-", "."): t for t in missing}
    symbols = list(names)
    for i in range(0, len(symbols), 100):
        chunk = tuple(symbols[i : i + 100])
        try:
            frames, provenance = provider.minute_bars(
                chunk, start, start + timedelta(days=1), "1Day", adjustment="raw", feed="sip"
            )
        except FeedError as exc:
            run.errors.append(str(exc))
            continue
        with engine.begin() as conn:
            fetch_id = add_fetch(conn, provenance)
            for symbol, frame in frames.items():
                ticker = names.get(symbol)
                same = frame[frame["time"].dt.date == day] if ticker else frame.iloc[0:0]
                if same.empty:
                    continue
                bar = same.iloc[-1]
                previous = missing[ticker].previous
                if previous and abs(bar["close"] / previous - 1) > SPLIT_SUSPECT:
                    run.errors.append(
                        f"{ticker}: {bar['close']:.2f} after {previous:.2f}, left to Tiingo"
                    )
                    # Handing a likely split to Tiingo is the intended outcome, not a failed
                    # fetch, so it must not turn the run into an error on its own.
                    run.attempted -= 1
                    continue
                conn.execute(
                    text(
                        """INSERT INTO price_bars (fetch_id, security_id, market_date,
                             market_timestamp, open, high, low, close, volume, div_cash,
                             split_factor)
                           VALUES (:f, :s, :d, :ts, :o, :h, :l, :c, :v, 0, 1)"""
                    ),
                    {
                        "f": fetch_id,
                        "s": missing[ticker].id,
                        "d": day,
                        "ts": session_close(day),
                        "o": float(bar["open"]),
                        "h": float(bar["high"]),
                        "l": float(bar["low"]),
                        "c": float(bar["close"]),
                        "v": float(bar["volume"]),
                    },
                )
                run.ok += 1
                run.added += 1
    return run.finish()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "feed",
        choices=["universe", "prices", "alpaca-closes", "history", "economic", "market-history"],
    )
    parser.add_argument("--limit", type=int, default=45, help="stocks per run")
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
        elif args.feed == "alpaca-closes":
            alpaca = AlpacaProvider(settings.alpaca_api_key_id, settings.alpaca_api_secret_key)
            status = run_alpaca_closes(engine, alpaca, now)
        elif args.feed == "market-history":
            status = run_market_history(engine, FrenchProvider())
        else:
            status = run_economic(engine, FredProvider(settings.fred_api_key))
    except FeedError as exc:  # For example, a missing key.
        status = Run(engine, args.feed).finish(str(exc))
    record_heartbeat(engine)
    if status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
