"""Alerts for held and watched stocks. Run after each price update.

    python -m stockintel.monitor          Create new alerts and print unsent ones.

Each alert has a key, so the same event never alerts twice.
"""

import itertools
import sys
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Engine, text

from stockintel.db import get_engine
from stockintel.market import latest_expected_session
from stockintel.tools import read_items

MOVE_LIMIT = 3.0


def add(conn, ticker, kind, message, key) -> None:
    conn.execute(
        text(
            """INSERT INTO alerts (ticker, kind, message, dedupe_key)
               VALUES (:ticker, :kind, :message, :key) ON CONFLICT (dedupe_key) DO NOTHING"""
        ),
        {"ticker": ticker, "kind": kind, "message": message, "key": key},
    )


def followed(conn) -> list:
    return conn.execute(
        text(
            """SELECT s.id, s.ticker, p.target_price, p.stop_price, p.buy_price
               FROM securities s
               LEFT JOIN positions p ON p.security_id = s.id
               LEFT JOIN watchlist w ON w.security_id = s.id
               WHERE p.security_id IS NOT NULL OR w.security_id IS NOT NULL"""
        )
    ).all()


def closes(conn, security_id: int, today: date) -> list[tuple[date, float]]:
    rows = conn.execute(
        text(
            """SELECT DISTINCT ON (market_date) market_date, close, split_factor
               FROM price_bars WHERE security_id = :id AND market_date >= :since
               ORDER BY market_date DESC, id DESC"""
        ),
        {"id": security_id, "since": today - timedelta(days=120)},
    ).all()
    return [(row.market_date, row.close / row.split_factor) for row in rows]


def check_price(conn, stock, rows, day) -> None:
    close = rows[0][1]
    if stock.target_price and close >= stock.target_price:
        add(
            conn,
            stock.ticker,
            "target",
            f"{stock.ticker} closed at {close:.2f}, at or above your target of "
            f"{stock.target_price:.2f}.",
            f"target:{stock.ticker}:{stock.target_price}",
        )
    if stock.stop_price and close <= stock.stop_price:
        add(
            conn,
            stock.ticker,
            "stop",
            f"{stock.ticker} closed at {close:.2f}, at or below your stop of "
            f"{stock.stop_price:.2f}.",
            f"stop:{stock.ticker}:{stock.stop_price}",
        )
    if len(rows) >= 40:
        prices = [row[1] for row in rows[:61]]
        moves = [a / b - 1 for a, b in itertools.pairwise(prices)]
        typical = (sum(m * m for m in moves[1:]) / len(moves[1:])) ** 0.5
        if typical and abs(moves[0]) > MOVE_LIMIT * typical:
            add(
                conn,
                stock.ticker,
                "move",
                f"{stock.ticker} moved {moves[0] * 100:+.1f}% on {day}, more than three times "
                "its usual daily move.",
                f"move:{stock.ticker}:{day}",
            )


def check_events(conn, stock, since: date) -> None:
    for row in conn.execute(
        text(
            """SELECT form, filing_date, accession_number, document_url FROM filings
               WHERE security_id = :id AND filing_date >= :since"""
        ),
        {"id": stock.id, "since": since},
    ):
        add(
            conn,
            stock.ticker,
            "filing",
            f"{stock.ticker} filed a {row.form} on {row.filing_date}: {row.document_url}",
            f"filing:{row.accession_number}",
        )
    for row in conn.execute(
        text(
            """SELECT items, filing_date, accession_number, document_url FROM filing_events
               WHERE security_id = :id AND filing_date >= :since"""
        ),
        {"id": stock.id, "since": since},
    ):
        for event in read_items(row.items):
            if event["serious"]:
                add(
                    conn,
                    stock.ticker,
                    "event",
                    f"{stock.ticker}: {event['meaning']} ({row.filing_date}): {row.document_url}",
                    f"event:{row.accession_number}:{event['item']}",
                )
    for row in conn.execute(
        text(
            """SELECT owner, shares, price, accession_number, line FROM insider_transactions
               WHERE security_id = :id AND filed >= :since AND code = 'P'"""
        ),
        {"id": stock.id, "since": since},
    ):
        add(
            conn,
            stock.ticker,
            "insider",
            f"{row.owner} bought {row.shares:,.0f} {stock.ticker} shares on the open market.",
            f"insider:{row.accession_number}:{row.line}",
        )


def check_fed(conn, today: date) -> None:
    day = conn.execute(
        text(
            """SELECT min(decision_date) FROM fed_meetings
               WHERE decision_date BETWEEN :today AND :limit"""
        ),
        {"today": today, "limit": today + timedelta(days=1)},
    ).scalar()
    if day:
        add(conn, None, "fed", f"The Fed announces a rate decision on {day}.", f"fed:{day}")


def scan(engine: Engine, now: datetime) -> int:
    day = latest_expected_session(now)
    since = now.date() - timedelta(days=3)
    with engine.begin() as conn:
        check_fed(conn, now.date())
        for stock in followed(conn):
            rows = closes(conn, stock.id, now.date())
            if rows and rows[0][0] >= day - timedelta(days=4):
                check_price(conn, stock, rows, rows[0][0])
            check_events(conn, stock, since)
        failed = conn.execute(
            text(
                """SELECT DISTINCT ON (feed) feed, status, started_at::date AS day
                   FROM feed_runs ORDER BY feed, id DESC"""
            )
        ).all()
        for row in failed:
            if row.status == "error" and row.feed != "prices":
                add(
                    conn,
                    None,
                    "feed",
                    f"The {row.feed} data feed failed on {row.day}.",
                    f"feed:{row.feed}:{row.day}",
                )
    from stockintel import changes, queries

    holdings = queries.holdings_today(engine, now)
    with engine.begin() as conn:
        for item in holdings:
            if item["call"] == "Not verified":
                continue
            conn.execute(
                text(
                    """INSERT INTO holding_calls (ticker, day, call, reason)
                       VALUES (:ticker, :day, :call, :reason)
                       ON CONFLICT (ticker, day) DO UPDATE SET call = EXCLUDED.call,
                         reason = EXCLUDED.reason"""
                ),
                {
                    "ticker": item["ticker"],
                    "day": now.date(),
                    "call": item["call"],
                    "reason": item["reason"],
                },
            )
    update = changes.build(engine, now.date())
    with engine.begin() as conn:
        for item in holdings:
            if item["call"] == "Sell":
                add(
                    conn,
                    item["ticker"],
                    "sell",
                    f"Sell: {item['ticker']}. {item['reason']}",
                    f"sell:{item['ticker']}:{now.date()}",
                )
        for row in update["yours"]:
            add(
                conn,
                row["ticker"],
                "change",
                f"{row['ticker']} changed. {row['topic']}: {row['was'] or 'new'} to {row['now']}. "
                f"{row['why']}",
                f"change:{row['ticker']}:{row['topic']}:{row['now']}:{now.date()}",
            )
        return conn.execute(text("SELECT count(*) FROM alerts WHERE NOT sent")).scalar()


def take_unsent(engine: Engine) -> list[str]:
    """Return unsent alerts and mark them sent."""
    with engine.begin() as conn:
        return list(
            conn.execute(
                text("UPDATE alerts SET sent = true WHERE NOT sent RETURNING message")
            ).scalars()
        )


def main() -> None:
    engine = get_engine()
    scan(engine, datetime.now(UTC))
    messages = take_unsent(engine)
    if messages:
        print("\n".join(f"- {message}" for message in messages))
    sys.exit(0)


if __name__ == "__main__":
    main()
