"""Read stored records for the API. Every value carries its provenance."""

from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import backtest, charts, explain, signals
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
        result["signals"] = signals.build_signals(
            charts.detect_patterns(frame), records_for(engine, timeframe)
        )
    return result


def latest_backtest(engine: Engine) -> dict | None:
    with engine.connect() as conn:
        run = conn.execute(text("SELECT * FROM backtest_runs ORDER BY id DESC LIMIT 1")).first()
        if run is None:
            return None
        results = _rows(
            conn.execute(
                text(
                    """SELECT * FROM backtest_results WHERE run_id = :id
                       ORDER BY edge DESC, horizon, signal, direction"""
                ),
                {"id": run.id},
            )
        )
    return {**dict(run._mapping), "results": results}


def records_for(engine: Engine, timeframe: str) -> dict[str, signals.TestedRecord]:
    """Tested records for signals. Only daily signals have been tested."""
    latest = latest_backtest(engine)
    if latest is None or timeframe != "daily":
        return {}
    return {
        f"{row['signal']}:{row['direction']}": signals.TestedRecord(
            row["sample_size"],
            row["oos_win_rate"] if row["oos_win_rate"] is not None else row["win_rate"],
            row["oos_baseline_win_rate"]
            if row["oos_baseline_win_rate"] is not None
            else row["baseline_win_rate"],
            row["edge"],
        )
        for row in latest["results"]
        if row["horizon"] == backtest.PRIMARY_HORIZON
    }


def stock_forecast(engine: Engine, ticker: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT f.* FROM forecasts f JOIN securities s ON s.id = f.security_id
                   WHERE s.ticker = :ticker ORDER BY f.target_session DESC LIMIT 1"""
            ),
            {"ticker": ticker.upper()},
        ).first()
    return {**dict(row._mapping), "action": action(row.rank_edge, row.rank_20d)} if row else None


def action(rank_edge: bool, rank: float | None) -> str:
    """The call shown to the user. Named only when the ranking has passed testing."""
    if not rank_edge or rank is None:
        return "No reliable edge"
    if rank >= 0.9:
        return "Buy candidate"
    return "Sell candidate" if rank <= 0.1 else "No action"


def ideas(engine: Engine) -> dict:
    """Stocks ranked for the next 20 days, only named if the ranking passed testing."""
    with engine.connect() as conn:
        target = conn.execute(text("SELECT max(target_session) FROM forecasts")).scalar()
        if target is None:
            return {"target_session": None, "edge": False, "buy": [], "sell": []}
        rows = _rows(
            conn.execute(
                text(
                    """SELECT s.ticker, s.name, f.rank_20d, f.rank_edge
                       FROM forecasts f JOIN securities s ON s.id = f.security_id
                       WHERE f.target_session = :target ORDER BY f.rank_20d DESC"""
                ),
                {"target": target},
            )
        )
    edge = bool(rows and rows[0]["rank_edge"])
    return {
        "target_session": target,
        "edge": edge,
        "buy": [row for row in rows if row["rank_20d"] >= 0.9] if edge else [],
        "sell": [row for row in rows if row["rank_20d"] <= 0.1] if edge else [],
    }


def track_record(engine: Engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """SELECT count(*) AS scored, avg(brier) AS brier,
                     avg(baseline_brier) AS baseline_brier,
                     avg(in_range::int) AS range_hit_rate FROM forecast_scores"""
            )
        ).first()
        written = conn.execute(text("SELECT count(*) FROM forecasts")).scalar()
        evaluations = _rows(
            conn.execute(
                text("SELECT DISTINCT ON (model) * FROM model_evaluations ORDER BY model, id DESC")
            )
        )
    return {**dict(row._mapping), "written": written, "evaluations": evaluations}


def stock_story(engine: Engine, ticker: str) -> list[dict] | None:
    data = chart(engine, ticker, "daily")
    if data is None:
        return None
    return explain.story(
        data["summary"],
        data["signals"],
        data["signals_blocked"],
        stock_forecast(engine, ticker),
        latest_evaluations(engine),
    )


def latest_evaluations(engine: Engine) -> dict[str, dict]:
    query = "SELECT DISTINCT ON (model) * FROM model_evaluations ORDER BY model, id DESC"
    with engine.connect() as conn:
        return {row.model: dict(row._mapping) for row in conn.execute(text(query))}
