"""Read stored records for the API. Every value carries its provenance."""

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import charts, signals
from stockintel.market import is_stale, latest_expected_session

FEEDS = {
    "universe": "SEC EDGAR",
    "prices": "Tiingo",
    "filings": "SEC EDGAR",
    "economic": "FRED",
}
PROVENANCE = "d.name AS source, f.source_url, f.retrieved_at, f.data_status"
JOIN = "JOIN fetches f ON f.id = r.fetch_id JOIN data_sources d ON d.id = f.source_id"


def _rows(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


def feeds(engine: Engine) -> list[dict]:
    """The latest run of each feed, and its last clean run."""
    output = []
    with engine.connect() as conn:
        for feed, source in FEEDS.items():
            latest = conn.execute(
                text("SELECT * FROM feed_runs WHERE feed = :feed ORDER BY id DESC LIMIT 1"),
                {"feed": feed},
            ).first()
            last_ok = conn.execute(
                text(
                    """SELECT max(finished_at) FROM feed_runs
                       WHERE feed = :feed AND status = 'ok'"""
                ),
                {"feed": feed},
            ).scalar()
            output.append(
                {
                    "feed": feed,
                    "source": source,
                    "status": latest.status if latest else "never_run",
                    "message": latest.message if latest else None,
                    "last_run": latest.started_at if latest else None,
                    "records_added": latest.records_added if latest else None,
                    "last_ok": last_ok,
                }
            )
    return output


def search(engine: Engine, query: str) -> list[dict]:
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    """SELECT ticker, name, exchange FROM securities
                       WHERE ticker ILIKE :prefix OR name ILIKE :anywhere
                       ORDER BY universe_rank LIMIT 20"""
                ),
                {"prefix": f"{query}%", "anywhere": f"%{query}%"},
            )
        )


def stock(engine: Engine, ticker: str) -> dict | None:
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT * FROM securities WHERE ticker = :ticker"), {"ticker": ticker.upper()}
        ).first()
        if security is None:
            return None
        bars = _rows(
            conn.execute(
                text(
                    f"""SELECT * FROM (
                          SELECT DISTINCT ON (r.market_date) r.market_date, r.market_timestamp,
                            r.open, r.high, r.low, r.close, r.volume, r.div_cash,
                            r.split_factor, {PROVENANCE}
                          FROM price_bars r {JOIN} WHERE r.security_id = :id
                          ORDER BY r.market_date DESC, r.id DESC LIMIT 30) t
                        ORDER BY market_date DESC"""
                ),
                {"id": security.id},
            )
        )
        filings = _rows(
            conn.execute(
                text(
                    f"""SELECT r.form, r.filing_date, r.report_date, r.accepted_at,
                          r.document_url, {PROVENANCE}
                        FROM filings r {JOIN} WHERE r.security_id = :id
                        ORDER BY r.filing_date DESC, r.id DESC LIMIT 20"""
                ),
                {"id": security.id},
            )
        )
    now = datetime.now(UTC)
    latest = bars[0]["market_date"] if bars else None
    return {
        "ticker": security.ticker,
        "name": security.name,
        "exchange": security.exchange,
        "latest_expected_session": latest_expected_session(now),
        "stale": is_stale(latest, now),
        "bars": bars,
        "filings": filings,
    }


def economic(engine: Engine) -> list[dict]:
    """The newest observation of each series, as currently published."""
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    f"""SELECT DISTINCT ON (r.series_id) r.series_id, r.observation_date,
                          r.realtime_start, r.value, {PROVENANCE}
                        FROM economic_observations r {JOIN}
                        ORDER BY r.series_id, r.observation_date DESC, r.realtime_start DESC"""
                )
            )
        )


def issues(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    """SELECT feed, kind, ticker, market_date, detail, detected_at
                       FROM validation_issues ORDER BY id DESC LIMIT 50"""
                )
            )
        )


def chart(engine: Engine, ticker: str, timeframe: str) -> dict | None:
    """Candles, indicators, levels and signals, computed only from stored bars."""
    with engine.connect() as conn:
        security = conn.execute(
            text("SELECT id, ticker, name FROM securities WHERE ticker = :ticker"),
            {"ticker": ticker.upper()},
        ).first()
        if security is None:
            return None
        rows = conn.execute(
            text(
                """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                     volume, div_cash, split_factor
                   FROM price_bars WHERE security_id = :id
                   ORDER BY market_date, id DESC"""
            ),
            {"id": security.id},
        ).all()
    now = datetime.now(UTC)
    latest = rows[-1].market_date if rows else None
    stale = is_stale(latest, now)
    result = {
        "ticker": security.ticker,
        "name": security.name,
        "timeframe": timeframe,
        "stale": stale,
        "latest_bar": latest,
        "latest_expected_session": latest_expected_session(now),
        "candles": [],
        "levels": [],
        "summary": None,
        "signals": [],
        "signals_blocked": stale,
    }
    if not rows:
        return result
    frame = charts.resample(charts.adjust(pd.DataFrame([row._mapping for row in rows])), timeframe)
    close = frame["close"]
    lines = charts.macd(close)
    computed = frame.assign(
        sma20=charts.sma(close, 20),
        sma50=charts.sma(close, 50),
        sma200=charts.sma(close, 200),
        rsi=charts.rsi(close),
        macd=lines["macd"],
        macd_signal=lines["signal"],
        macd_histogram=lines["histogram"],
    )
    # Blank warm-up values stay blank. They are never filled.
    records = computed.astype(object).where(computed.notna(), None).to_dict("records")
    result["candles"] = records
    found = charts.levels(frame)
    result["levels"] = [level.__dict__ for level in found]
    result["summary"] = charts.summary(frame, found)
    if not stale:
        result["signals"] = signals.build_signals(charts.detect_patterns(frame), {})
    return result
