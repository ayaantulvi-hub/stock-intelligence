"""Print the tracked companies, largest first, with their latest close and ranking.

Run: python -m stockintel.lists [count]
"""

import sys

from sqlalchemy import text

from stockintel.db import get_engine

QUERY = """
SELECT s.universe_rank, s.ticker, s.name, s.exchange,
  (SELECT p.close / p.split_factor FROM price_bars p WHERE p.security_id = s.id
   ORDER BY p.market_date DESC, p.id DESC LIMIT 1) AS close,
  (SELECT f.rank_20d FROM forecasts f WHERE f.security_id = s.id
   ORDER BY f.target_session DESC LIMIT 1) AS rank
FROM securities s ORDER BY s.universe_rank LIMIT :n
"""


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    with get_engine().connect() as conn:
        total = conn.execute(text("SELECT count(*) FROM securities")).scalar()
        print(f"tracked {total}")
        for row in conn.execute(text(QUERY), {"n": count}):
            close = "Not verified" if row.close is None else f"{row.close:.2f}"
            rank = "none" if row.rank is None else f"{row.rank:.2f}"
            print(f"{row.universe_rank}|{row.ticker}|{row.name}|{row.exchange}|{close}|{rank}")


if __name__ == "__main__":
    main()
