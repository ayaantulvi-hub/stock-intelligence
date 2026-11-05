"""What changed since the last update: decisions, lists and company news.

Each item compares two stored results, so nothing here is new analysis. Stocks you own or
watch come first. A stock with no earlier result isn't reported as a change.
"""

from datetime import date, timedelta

from sqlalchemy import Engine, text

from stockintel import advice, horizons, tools

TOP = 10
EVENT_DAYS = 3
BETTER, WORSE, NEUTRAL = "buy", "sell", "neutral"
LEAN_ORDER = {"Sell": 0, "Hold off": 1, "Mixed": 2, "No lean": 2, "Buy": 3}


def item(ticker, topic, was, now, why, tone):
    return {"ticker": ticker, "topic": topic, "was": was, "now": now, "why": why, "tone": tone}


def lean_changes(old: dict, new: dict) -> list[dict]:
    """Moves in the model's lean, and into or out of the top of the list."""
    found = []
    for ticker, (rank, action) in new.items():
        if ticker not in old:
            continue
        was = advice.overall(old[ticker][1], old[ticker][0])["lean"]
        now = advice.overall(action, rank)["lean"]
        if was != now:
            tone = BETTER if LEAN_ORDER.get(now, 2) > LEAN_ORDER.get(was, 2) else WORSE
            found.append(item(ticker, "Model lean", was, now, "Its ranking moved.", tone))

    def top(group):
        ranked = [t for t, value in group.items() if value[0] is not None]
        return set(sorted(ranked, key=lambda t: -group[t][0])[:TOP])

    shared = {ticker: value for ticker, value in old.items() if ticker in new}
    was_top, now_top = top(shared), top(new)
    for ticker in sorted(now_top - was_top):
        if ticker in shared:
            found.append(
                item(ticker, "Top 10", "Outside", "In the top 10", "New on today's list.", BETTER)
            )
    for ticker in sorted(was_top - now_top):
        found.append(
            item(ticker, "Top 10", "In the top 10", "Outside", "Left today's list.", WORSE)
        )
    return found


def review_changes(old: dict, new: dict) -> list[dict]:
    """Changes in expert overrides, long-term answers and short-term signals."""
    found = []
    for ticker, now in new.items():
        was = old.get(ticker)
        if was is None:
            continue
        if now["blocked"] and not was["blocked"]:
            found.append(item(ticker, "Warning", "None", "Hold off", now["blocked"], WORSE))
        if was["blocked"] and not now["blocked"]:
            found.append(item(ticker, "Warning", "Hold off", "Cleared", was["blocked"], BETTER))
        before = horizons.invest({"lenses": was["detail"], "blocked": was["blocked"]})
        after = horizons.invest({"lenses": now["detail"], "blocked": now["blocked"]})
        if before["call"] != after["call"]:
            tone = {"buy": BETTER, "sell": WORSE}.get(after["kind"], NEUTRAL)
            found.append(
                item(ticker, "Long-term", before["call"], after["call"], after["reason"], tone)
            )
        was_short = (was["short"] or {}).get("call")
        now_short = (now["short"] or {}).get("call")
        if was_short and now_short and was_short != now_short:
            kind = (now["short"] or {}).get("kind")
            tone = {"buy": BETTER, "sell": WORSE}.get(kind, NEUTRAL)
            found.append(
                item(ticker, "Short trade", was_short, now_short, now["short"]["reason"], tone)
            )
    return found


def _forecasts(conn) -> tuple[date | None, date | None, dict, dict]:
    from stockintel.queries import action

    days = list(
        conn.execute(
            text("SELECT DISTINCT target_session FROM forecasts ORDER BY 1 DESC LIMIT 2")
        ).scalars()
    )
    if len(days) < 2:
        return (days[0] if days else None), None, {}, {}
    query = """SELECT s.ticker, f.target_session, f.rank_20d, f.rank_edge
               FROM forecasts f JOIN securities s ON s.id = f.security_id
               WHERE f.target_session IN (:a, :b)"""
    new, old = {}, {}
    for row in conn.execute(text(query), {"a": days[0], "b": days[1]}):
        group = new if row.target_session == days[0] else old
        group[row.ticker] = (row.rank_20d, action(row.rank_edge, row.rank_20d))
    return days[0], days[1], old, new


def _reviews(conn) -> tuple[dict, dict]:
    days = list(
        conn.execute(
            text("SELECT DISTINCT review_date FROM expert_reviews ORDER BY 1 DESC LIMIT 2")
        ).scalars()
    )
    if len(days) < 2:
        return {}, {}
    query = """SELECT DISTINCT ON (r.security_id, r.review_date) s.ticker, r.review_date,
                 r.blocked, r.detail, r.short_term
               FROM expert_reviews r JOIN securities s ON s.id = r.security_id
               WHERE r.review_date IN (:a, :b)
               ORDER BY r.security_id, r.review_date, r.id DESC"""
    new, old = {}, {}
    for row in conn.execute(text(query), {"a": days[0], "b": days[1]}):
        group = new if row.review_date == days[0] else old
        group[row.ticker] = {
            "blocked": row.blocked,
            "detail": row.detail,
            "short": row.short_term,
        }
    return old, new


def _holding_changes(conn) -> list[dict]:
    query = """WITH ranked AS (
                 SELECT ticker, call, reason, day,
                   row_number() OVER (PARTITION BY ticker ORDER BY day DESC) AS place
                 FROM holding_calls)
               SELECT a.ticker, a.call, a.reason, b.call AS before
               FROM ranked a JOIN ranked b ON a.ticker = b.ticker
               WHERE a.place = 1 AND b.place = 2 AND a.call <> b.call"""
    return [
        item(
            row.ticker,
            "Your holding",
            row.before,
            row.call,
            row.reason,
            WORSE if row.call == "Sell now" else NEUTRAL if row.call == "Wait" else BETTER,
        )
        for row in conn.execute(text(query))
    ]


def _company_news(conn, tickers: set[str], today: date) -> list[dict]:
    if not tickers:
        return []
    query = """SELECT s.ticker, e.filing_date, e.items FROM filing_events e
               JOIN securities s ON s.id = e.security_id
               WHERE e.filing_date >= :since AND s.ticker = ANY(:tickers)
               ORDER BY e.filing_date DESC"""
    found = []
    rows = conn.execute(
        text(query), {"since": today - timedelta(days=EVENT_DAYS), "tickers": sorted(tickers)}
    )
    for row in rows:
        for event in tools.read_items(row.items):
            if event["serious"] or event["item"] == "2.02":
                found.append(
                    item(
                        row.ticker,
                        "Company news",
                        "",
                        event["meaning"],
                        f"Filed {row.filing_date}.",
                        WORSE if event["serious"] else NEUTRAL,
                    )
                )
    return found


def build(engine: Engine, today: date) -> dict:
    with engine.connect() as conn:
        latest, previous, old_ranks, new_ranks = _forecasts(conn)
        old_reviews, new_reviews = _reviews(conn)
        followed = set(
            conn.execute(
                text(
                    """SELECT s.ticker FROM securities s
                       LEFT JOIN positions p ON p.security_id = s.id
                       LEFT JOIN watchlist w ON w.security_id = s.id
                       WHERE p.security_id IS NOT NULL OR w.security_id IS NOT NULL"""
                )
            ).scalars()
        )
        held = _holding_changes(conn)
        news = _company_news(conn, followed, today)
    found = held + news + lean_changes(old_ranks, new_ranks)
    found += review_changes(old_reviews, new_reviews)
    for row in found:
        row["yours"] = row["ticker"] in followed
    yours = [row for row in found if row["yours"]]
    others = [row for row in found if not row["yours"]]
    return {"latest": latest, "previous": previous, "yours": yours, "others": others}
