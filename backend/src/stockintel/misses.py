"""When a forecast is wrong, record the likeliest reason from stored records.

Only stored facts are used. If nothing explains a large move, the reason says so, because a
guess here would teach the wrong lesson.

Runs after each scoring.
"""

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel.tools import read_items

NOISE = "Ordinary daily swing, within its normal range"
RESULTS = "The company reported results"
MARKET = "The whole market moved the same way"
INDUSTRY = "Its industry moved the same way"
GAP = "It jumped at the open. No cause is stored"
UNKNOWN = "Unusually large move. No cause is stored"


def was_wrong(row) -> bool:
    chances = {"up": row.p_up, "flat": row.p_flat, "down": row.p_down}
    return max(chances, key=chances.get) != row.outcome or not row.in_range


def reason(
    change: float,
    gap: float | None,
    typical: float | None,
    market: float | None,
    peers: float | None,
    items: list[str],
) -> str:
    """The first explanation that fits, strongest evidence first."""
    if any("2.02" in item for item in items):
        return RESULTS
    for item in items:
        events = [event for event in read_items(item) if event["item"] != "8.01"]
        if events:
            return f"Company filing: {events[0]['meaning']}"

    def same_way(other):
        return other is not None and other * change > 0

    if same_way(market) and abs(market) >= 0.01 and abs(market) >= abs(change) * 0.4:
        return MARKET
    if same_way(peers) and abs(peers) >= 0.015 and abs(peers) >= abs(change) * 0.4:
        return INDUSTRY
    if typical and gap is not None and abs(gap) >= 2 * typical:
        return GAP
    if typical and abs(change) >= 3 * typical:
        return UNKNOWN
    return NOISE


def run(engine: Engine) -> int:
    query = """SELECT f.id, f.security_id, f.as_of_session, f.target_session, f.p_up, f.p_flat,
                 f.p_down, f.last_close, s.outcome, s.in_range, s.actual_close, c.sic, c.ticker
               FROM forecast_scores s JOIN forecasts f ON f.id = s.forecast_id
               JOIN securities c ON c.id = f.security_id
               LEFT JOIN forecast_misses m ON m.forecast_id = f.id
               WHERE m.forecast_id IS NULL"""
    day_query = """
        SELECT DISTINCT ON (b.security_id, b.market_date) b.security_id, b.market_date, b.open,
          b.close, b.div_cash, b.split_factor, s.sic
        FROM price_bars b JOIN securities s ON s.id = b.security_id
        WHERE b.market_date IN (:then, :day) ORDER BY b.security_id, b.market_date, b.id DESC"""
    history = """SELECT market_date, close / split_factor AS close FROM
                 (SELECT DISTINCT ON (market_date) market_date, close, split_factor FROM price_bars
                  WHERE security_id = :id AND market_date < :day
                  ORDER BY market_date DESC, id DESC LIMIT 61) AS recent ORDER BY market_date"""
    events = """SELECT items FROM filing_events WHERE security_id = :id
                AND filing_date BETWEEN :then AND :day"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    wrong, cached = 0, {}
    with engine.begin() as conn:
        for row in rows:
            if not was_wrong(row):
                conn.execute(
                    text("INSERT INTO forecast_misses (forecast_id, reason) VALUES (:i, NULL)"),
                    {"i": row.id},
                )
                continue
            key = (row.as_of_session, row.target_session)
            if key not in cached:
                bars = pd.DataFrame(
                    [
                        item._mapping
                        for item in conn.execute(text(day_query), {"then": key[0], "day": key[1]})
                    ]
                )
                now = bars[bars["market_date"] == key[1]].set_index("security_id")
                was = bars[bars["market_date"] == key[0]].set_index("security_id")
                moves = (now["close"] * now["split_factor"] + now["div_cash"]) / was["close"] - 1
                cached[key] = (now, was, moves.dropna())
            now, was, moves = cached[key]
            if row.security_id not in moves.index:
                continue
            change = float(moves[row.security_id])
            bar = now.loc[row.security_id]
            gap = float(bar["open"] * bar["split_factor"] / was.loc[row.security_id, "close"] - 1)
            past = pd.DataFrame(
                [
                    item._mapping
                    for item in conn.execute(
                        text(history), {"id": row.security_id, "day": row.target_session}
                    )
                ]
            )
            typical = None
            if len(past) > 20:
                typical = float(np.nanstd(past["close"].pct_change(fill_method=None)))
            group = None
            if row.sic is not None:
                peers = now.index[(now["sic"] // 100 == row.sic // 100)]
                peers = moves.reindex(peers).dropna().drop(row.security_id, errors="ignore")
                group = float(peers.median()) if len(peers) >= 3 else None
            items = list(
                conn.execute(
                    text(events),
                    {"id": row.security_id, "then": row.as_of_session, "day": row.target_session},
                ).scalars()
            )
            found = reason(change, gap, typical, float(moves.median()), group, items)
            conn.execute(
                text(
                    """INSERT INTO forecast_misses (forecast_id, reason, change_percent)
                       VALUES (:i, :reason, :change)"""
                ),
                {"i": row.id, "reason": found, "change": change * 100},
            )
            wrong += 1
    return wrong


def summary(engine: Engine) -> dict:
    query = """SELECT m.reason, count(*) AS count FROM forecast_misses m
               WHERE m.reason IS NOT NULL GROUP BY m.reason ORDER BY count(*) DESC"""
    recent = """SELECT s.ticker, f.target_session, m.reason, m.change_percent
                FROM forecast_misses m JOIN forecasts f ON f.id = m.forecast_id
                JOIN securities s ON s.id = f.security_id
                WHERE m.reason IS NOT NULL ORDER BY f.target_session DESC, f.id LIMIT 30"""
    with engine.connect() as conn:
        reasons = [dict(row._mapping) for row in conn.execute(text(query))]
        latest = [dict(row._mapping) for row in conn.execute(text(recent))]
        checked = conn.execute(text("SELECT count(*) FROM forecast_misses")).scalar()
    return {"checked": checked, "reasons": reasons, "recent": latest}
