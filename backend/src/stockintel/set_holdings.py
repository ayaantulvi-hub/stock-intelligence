"""Make the stored holdings match a list, for when the owner sends a whole portfolio.

The list arrives as JSON in the HOLDINGS environment variable. Each item needs ticker, shares and
buy_price, and may have stop_price and sell_by. Stocks not on the list are removed. Nothing changes
if any ticker is unknown.

Run: HOLDINGS='[...]' python -m stockintel.set_holdings
"""

import json
import os

from sqlalchemy import text
from sqlalchemy.engine import Engine

from stockintel.db import get_engine
from stockintel.queries import save_position


def apply(engine: Engine, items: list[dict]) -> list[str]:
    """Save the list and return its tickers."""
    tickers = [item["ticker"].upper() for item in items]
    if len(set(tickers)) != len(tickers):
        raise ValueError("A ticker appears twice in the list")
    with engine.connect() as conn:
        known = set(
            conn.execute(
                text("SELECT ticker FROM securities WHERE ticker = ANY(:t)"), {"t": tickers}
            ).scalars()
        )
    unknown = sorted(set(tickers) - known)
    if unknown:
        raise ValueError(f"Not tracked, so nothing was changed: {', '.join(unknown)}")
    with engine.begin() as conn:
        conn.execute(
            text(
                """DELETE FROM positions WHERE security_id NOT IN
                   (SELECT id FROM securities WHERE ticker = ANY(:t))"""
            ),
            {"t": tickers},
        )
    for item in items:
        save_position(
            engine,
            item["ticker"],
            {
                "shares": item["shares"],
                "buy_price": item["buy_price"],
                "target_price": None,
                "stop_price": item.get("stop_price"),
                "sell_by": item.get("sell_by"),
            },
        )
    return tickers


def main() -> None:
    engine = get_engine()
    apply(engine, json.loads(os.environ["HOLDINGS"]))
    query = """SELECT s.ticker, p.shares, p.buy_price, p.stop_price, p.sell_by
               FROM positions p JOIN securities s ON s.id = p.security_id ORDER BY s.ticker"""
    with engine.connect() as conn:
        for row in conn.execute(text(query)):
            print(row.ticker, row.shares, row.buy_price, row.stop_price, row.sell_by)


if __name__ == "__main__":
    main()
