"""Explain one stock's recent decisions, for checking a change. Never run it on a holding: the
job logs are public. Run: python -m stockintel.inspect_stock NVDA"""

import sys

from sqlalchemy import text

from stockintel.db import get_engine

if __name__ == "__main__":
    ticker = sys.argv[1].upper()
    with get_engine().connect() as conn:
        for row in conn.execute(
            text(
                """SELECT f.created_at, f.as_of_session, f.target_session, f.last_close,
                 round(f.rank_20d::numeric, 3) AS rank, f.beat_chance
               FROM forecasts f JOIN securities s ON s.id = f.security_id
               WHERE s.ticker = :t ORDER BY f.created_at DESC LIMIT 4"""
            ),
            {"t": ticker},
        ):
            print("FORECAST", dict(row._mapping))
        for row in conn.execute(
            text(
                """SELECT r.review_date, r.blocked, r.short_term->>'call' AS short_call,
                 r.short_term->>'reason' AS short_reason
               FROM expert_reviews r JOIN securities s ON s.id = r.security_id
               WHERE s.ticker = :t ORDER BY r.review_date DESC LIMIT 3"""
            ),
            {"t": ticker},
        ):
            print("REVIEW", dict(row._mapping))
        for row in conn.execute(
            text(
                """SELECT b.market_date, b.close FROM price_bars b JOIN securities s
               ON s.id = b.security_id WHERE s.ticker = :t ORDER BY b.market_date DESC LIMIT 3"""
            ),
            {"t": ticker},
        ):
            print("PRICE", dict(row._mapping))
        for row in conn.execute(
            text(
                """SELECT latest, count(*) FROM (SELECT max(market_date) AS latest FROM price_bars
               GROUP BY security_id) x GROUP BY latest ORDER BY latest DESC"""
            )
        ):
            print("FRESHNESS", dict(row._mapping))
        for row in conn.execute(
            text(
                """SELECT started_at, status, message FROM feed_runs WHERE feed = 'judge'
               ORDER BY id DESC LIMIT 3"""
            )
        ):
            print("JUDGE", dict(row._mapping))
