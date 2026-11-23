"""Read-only queries behind the dashboard."""

from sqlalchemy import text
from sqlalchemy.engine import Engine

# Feed name -> who publishes the data.
FEEDS = {
    "prices": "Tiingo",
    "alpaca closes": "Alpaca (consolidated feed)",
    "universe": "SEC EDGAR",
    "history": "SEC EDGAR (public float)",
    "economic": "FRED (Federal Reserve Bank of St. Louis)",
}


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
                text("SELECT max(finished_at) FROM feed_runs WHERE feed = :feed AND status = 'ok'"),
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


def quant_results(engine: Engine) -> list[dict]:
    """The latest stored result for each quant study and variant."""
    query = """SELECT DISTINCT ON (study, variant) study, variant, run_at, period, verdict,
                 metrics, settings
               FROM quant_results ORDER BY study, variant, run_at DESC"""
    with engine.connect() as conn:
        return [dict(row._mapping) for row in conn.execute(text(query))]


def coverage(engine: Engine) -> dict:
    """How much data the studies stand on: stocks, how many have an industry code (pairs trading
    needs one), price rows and the date range."""
    query = """SELECT (SELECT count(*) FROM securities) AS stocks,
                 (SELECT count(*) FROM securities WHERE sic IS NOT NULL) AS with_industry,
                 (SELECT count(*) FROM price_bars) AS price_rows,
                 (SELECT min(market_date) FROM price_bars) AS first_day,
                 (SELECT max(market_date) FROM price_bars) AS last_day"""
    with engine.connect() as conn:
        return dict(conn.execute(text(query)).one()._mapping)
