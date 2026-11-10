"""List the stocks with no decision for the latest target session, and the likely reason.

Prints tickers and price-history facts only, never holdings. Run: python -m stockintel.missing_decisions
"""

from sqlalchemy import text

from stockintel.db import get_engine


def main() -> None:
    query = """WITH target AS (SELECT max(target_session) AS day FROM forecasts)
               SELECT s.ticker, s.exchange, count(p.id) AS bars, min(p.market_date) AS first,
                 max(p.market_date) AS last
               FROM securities s LEFT JOIN price_bars p ON p.security_id = s.id
               WHERE NOT EXISTS (SELECT 1 FROM forecasts f, target t
                 WHERE f.security_id = s.id AND f.target_session = t.day)
               GROUP BY s.ticker, s.exchange ORDER BY s.ticker"""
    with get_engine().connect() as conn:
        for row in conn.execute(text(query)):
            print("MISSING", dict(row._mapping))


if __name__ == "__main__":
    main()
