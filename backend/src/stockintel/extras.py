"""Read-only views for Congress trades, short interest and the data checks."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, text

from stockintel import overrides, regime

CONGRESS_DAYS = 60


def congress(engine: Engine, ticker: str | None = None, days: int = CONGRESS_DAYS) -> dict:
    """Recent House trades in tracked stocks, newest filing first. Holdings are marked."""
    since = datetime.now(UTC).date() - timedelta(days=days)
    query = """SELECT c.member, c.owner, c.ticker, c.asset, c.action, c.trade_date, c.filed_date,
                 c.amount, c.days_to_file, c.url,
                 EXISTS (SELECT 1 FROM positions p WHERE p.security_id = s.id) AS owned
               FROM congress_trades c JOIN securities s ON s.ticker = c.ticker
               WHERE c.filed_date >= :since AND (CAST(:ticker AS text) IS NULL OR c.ticker = CAST(:ticker AS text))
               ORDER BY c.filed_date DESC, c.id DESC LIMIT 100"""
    with engine.connect() as conn:
        rows = [
            dict(r._mapping)
            for r in conn.execute(
                text(query), {"since": since, "ticker": ticker.upper() if ticker else None}
            )
        ]
        reports = conn.execute(
            text(
                """SELECT count(*) AS total, count(*) FILTER (WHERE NOT read_ok) AS unread,
                 max(filed_date) AS newest FROM congress_reports"""
            )
        ).first()
    return {
        "trades": rows,
        "reports_read": reports.total - reports.unread,
        "reports_unread": reports.unread,
        "newest_filing": reports.newest,
        "note": "House members only. Reports arrive up to 45 days after a trade, and amounts "
        "are ranges. Shown for context: not tested as a signal.",
    }


def short_interest(engine: Engine, ticker: str) -> dict | None:
    query = """SELECT si.settlement_date, si.short_shares, si.previous_short_shares,
                 si.avg_daily_volume, si.days_to_cover, f.source_url
               FROM short_interest si JOIN securities s ON s.id = si.security_id
               JOIN fetches f ON f.id = si.fetch_id
               WHERE s.ticker = :t ORDER BY si.settlement_date DESC LIMIT 1"""
    with engine.connect() as conn:
        row = conn.execute(text(query), {"t": ticker.upper()}).first()
    if row is None:
        return None
    out = dict(row._mapping)
    if row.previous_short_shares:
        out["change"] = row.short_shares / row.previous_short_shares - 1
    return out


def checks(engine: Engine) -> dict:
    query = """SELECT ticker, market_date, detail, detected_at FROM validation_issues
               WHERE kind = 'conflict' AND detected_at >= now() - interval '8 days'
               ORDER BY id DESC LIMIT 40"""
    with engine.connect() as conn:
        conflicts = [dict(r._mapping) for r in conn.execute(text(query))]
        last = conn.execute(
            text("SELECT max(started_at) FROM feed_runs WHERE feed = 'cross-check'")
        ).scalar()
    return {"conflicts": conflicts, "last_check": last, "overrides": overrides.latest(engine)}


def market_check(engine: Engine) -> dict | None:
    return regime.current(engine)


def decision_tests(engine: Engine) -> dict:
    """Which factor families help, and how often each ranking really beat the average stock."""
    with engine.connect() as conn:
        families = [
            dict(r._mapping)
            for r in conn.execute(
                text(
                    """SELECT family, change, t_stat, verdict, run_at FROM family_tests
               WHERE run_at = (SELECT max(run_at) FROM family_tests) ORDER BY t_stat DESC"""
                )
            )
        ]
        bins = [
            dict(r._mapping)
            for r in conn.execute(
                text(
                    """SELECT model, low, high, rate, n FROM rank_calibration
               WHERE run_at = (SELECT max(run_at) FROM rank_calibration) ORDER BY low"""
                )
            )
        ]
    return {"families": families, "calibration": bins}
