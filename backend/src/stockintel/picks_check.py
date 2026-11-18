"""How the model's Buy-level and Sell-level picks have done so far, against the average stock.

Covers every stock the model ranks, never holdings, so it is safe to print in a public log.
For each forecast day, stocks ranked 0.7 or above (Buy level) and 0.3 or below (Sell level) are
followed from that day's close to the latest close. Run: python -m stockintel.picks_check
"""

from sqlalchemy import text

from stockintel.db import get_engine

QUERY = """
WITH latest AS (
  SELECT DISTINCT ON (security_id) security_id, close / split_factor AS close, market_date
  FROM price_bars ORDER BY security_id, market_date DESC, id DESC),
picks AS (
  SELECT f.as_of_session, f.rank_20d, f.last_close, l.close AS now_close
  FROM forecasts f JOIN latest l USING (security_id)
  WHERE f.as_of_session >= :since AND f.rank_20d IS NOT NULL AND f.last_close > 0)
SELECT as_of_session,
  count(*) AS stocks,
  avg(now_close / last_close - 1) AS average_stock,
  avg(now_close / last_close - 1) FILTER (WHERE rank_20d >= 0.7) AS buy_level,
  avg(now_close / last_close - 1) FILTER (WHERE rank_20d <= 0.3) AS sell_level,
  avg((now_close > last_close)::int) FILTER (WHERE rank_20d >= 0.7) AS buy_level_up_share
FROM picks GROUP BY as_of_session ORDER BY as_of_session"""


def main() -> None:
    with get_engine().connect() as conn:
        for row in conn.execute(text(QUERY), {"since": "2026-10-26"}):
            r = row._mapping
            print(
                f"PICKS from {r['as_of_session']}: {r['stocks']} stocks | average "
                f"{r['average_stock']:+.2%} | Buy-level {r['buy_level']:+.2%} | Sell-level "
                f"{r['sell_level']:+.2%} | Buy-level still up {r['buy_level_up_share']:.0%}"
            )


if __name__ == "__main__":
    main()
