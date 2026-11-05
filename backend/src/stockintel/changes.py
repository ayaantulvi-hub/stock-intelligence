"""What changed since the last update: decisions, lists and company news.

Each item compares two stored results, so nothing here is new analysis. Stocks you own or
watch come first. A stock with no earlier result isn't reported as a change.
"""

from datetime import date, timedelta

from sqlalchemy import Engine, text

from stockintel import advice, horizons, tools
from stockintel.providers import news as feeds

TOP = 10
EVENT_DAYS = 3
BETTER, WORSE, NEUTRAL = "buy", "sell", "neutral"
CALL_ORDER = {
    "Don't buy": 0,
    "Leans don't buy": 1,
    "Hold off": 2,
    "Wait": 3,
    "Leans buy": 4,
    "Buy": 5,
}
MAIN_TOPICS = ("Decision", "Your holding")


def call_for(rank: float | None, action: str, blocked: str | None) -> str:
    """The same answer a stock's page gives someone who doesn't own it."""
    answer = advice.decision(action, rank, False, None)
    return advice.apply_experts(answer, {"blocked": blocked})["call"]


def item(ticker, topic, was, now, why, tone):
    return {"ticker": ticker, "topic": topic, "was": was, "now": now, "why": why, "tone": tone}


def lean_changes(
    old: dict, new: dict, old_blocks: dict | None = None, new_blocks: dict | None = None
) -> list[dict]:
    """Changes in the buy, wait or sell decision, and in the top of the list."""
    found = []
    for ticker, (rank, action) in new.items():
        if ticker not in old:
            continue
        was = call_for(old[ticker][0], old[ticker][1], (old_blocks or {}).get(ticker))
        now = call_for(rank, action, (new_blocks or {}).get(ticker))
        if was != now:
            tone = BETTER if CALL_ORDER.get(now, 3) > CALL_ORDER.get(was, 3) else WORSE
            found.append(item(ticker, "Decision", was, now, "Its ranking or checks moved.", tone))

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


def what_to_do(holding: dict | None, followed: bool) -> str:
    """The plain instruction beside each change, whatever the change was."""
    if holding is None:
        return "You don't own it, so nothing to do." if followed else "No action."
    if holding["call"] == "Sell now":
        return f"Sell now. {holding['reason']}"
    if holding["call"] == "Keep":
        return "Keep. Don't sell, your plan hasn't changed."
    return "Wait for today's prices."


def _followed_news(conn, tickers: set[str], today: date) -> list[dict]:
    """Headlines from the last day that name a stock you follow or its industry."""
    if not tickers:
        return []
    query = "SELECT s.ticker, s.sic FROM securities s WHERE s.ticker = ANY(:t)"
    groups: dict[str, str] = {}
    for ticker, sic in conn.execute(text(query), {"t": sorted(tickers)}):
        groups[ticker] = ticker
        industry = feeds.industry_of(sic)
        if industry:
            groups.setdefault(industry, ticker)
    rows = conn.execute(
        text(
            """SELECT DISTINCT ON (subject) subject, title, domain FROM news_articles
               WHERE subject = ANY(:s) AND seen_at >= :since ORDER BY subject, seen_at DESC"""
        ),
        {"s": sorted(groups), "since": today - timedelta(days=1)},
    )
    return [
        item(
            groups[row.subject],
            row.subject.replace("Industry: ", "") + " news"
            if row.subject.startswith("Industry")
            else "Company news",
            "",
            row.title[:110],
            row.domain,
            NEUTRAL,
        )
        for row in rows
    ]


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
        news += _followed_news(conn, followed, today)
    found = (
        held
        + news
        + lean_changes(
            old_ranks,
            new_ranks,
            {ticker: row["blocked"] for ticker, row in old_reviews.items()},
            {ticker: row["blocked"] for ticker, row in new_reviews.items()},
        )
    )
    found += review_changes(old_reviews, new_reviews)
    from stockintel.queries import holdings_today

    calls = {row["ticker"]: row for row in holdings_today(engine)}
    for row in found:
        row["yours"] = row["ticker"] in followed
        row["action"] = what_to_do(calls.get(row["ticker"]), row["yours"])
    decisions = [row for row in found if row["topic"] in MAIN_TOPICS]
    decisions.sort(key=lambda row: not row["yours"])
    details = [row for row in found if row["topic"] not in MAIN_TOPICS]
    return {
        "latest": latest,
        "previous": previous,
        "decisions": decisions,
        "details": details,
        "yours": [
            row
            for row in found
            if row["yours"] and row["topic"] != "Short trade" and not row["topic"].endswith(" news")
        ],
    }
