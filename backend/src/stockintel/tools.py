"""Portfolio, practice trading, journal, reliability, warning signs and market mood."""

from datetime import date, timedelta

from sqlalchemy import Engine, text

STARTING_CASH = 10000.0
MIN_LIVE_DAYS = 60
LATEST = """SELECT close, market_date FROM price_bars WHERE security_id = :id
            ORDER BY market_date DESC, id DESC LIMIT 1"""


def _rows(result) -> list[dict]:
    return [dict(row._mapping) for row in result]


def sector_name(sic: int | None) -> str:
    if sic is None:
        return "Not verified"
    group = sic // 100
    ranges = [
        (10, 14, "Energy and mining"),
        (15, 17, "Construction"),
        (20, 39, "Manufacturing and technology hardware"),
        (40, 49, "Transport, telecoms and utilities"),
        (50, 51, "Wholesale"),
        (52, 59, "Retail"),
        (60, 67, "Finance and property"),
        (70, 89, "Services and software"),
    ]
    return next((name for low, high, name in ranges if low <= group <= high), "Other")


def portfolio(engine: Engine) -> dict:
    query = """SELECT s.ticker, s.name, s.sic, p.shares, p.buy_price,
                 (SELECT b.close FROM price_bars b WHERE b.security_id = s.id
                  ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS price
               FROM positions p JOIN securities s ON s.id = p.security_id ORDER BY s.ticker"""
    with engine.connect() as conn:
        rows = _rows(conn.execute(text(query)))
    known = [row for row in rows if row["price"] is not None]
    worth = sum(row["shares"] * row["price"] for row in known)
    cost = sum(row["shares"] * row["buy_price"] for row in known)
    sectors: dict[str, float] = {}
    holdings = []
    for row in rows:
        value = None if row["price"] is None else row["shares"] * row["price"]
        sector = sector_name(row["sic"])
        if value is not None:
            sectors[sector] = sectors.get(sector, 0.0) + value
        holdings.append(
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "sector": sector,
                "shares": row["shares"],
                "buy_price": row["buy_price"],
                "price": row["price"],
                "worth": value,
                "profit": None if value is None else value - row["shares"] * row["buy_price"],
                "share_of_total": None if value is None or not worth else value / worth,
            }
        )
    risks = [
        f"{item['ticker']} is {item['share_of_total'] * 100:.0f}% of your holdings, above the "
        "usual 10% limit."
        for item in holdings
        if item["share_of_total"] and item["share_of_total"] > 0.10 and len(holdings) >= 10
    ]
    if 0 < len(holdings) < 10:
        risks.append(f"You hold {len(holdings)} stocks. One bad company can do real damage.")
    risks += [
        f"{name} is {value / worth * 100:.0f}% of your holdings."
        for name, value in sectors.items()
        if worth and value / worth > 0.4 and len(holdings) > 1
    ]
    return {
        "worth": worth,
        "cost": cost,
        "profit": worth - cost,
        "holdings": holdings,
        "sectors": [
            {"sector": name, "share": value / worth} for name, value in sorted(sectors.items())
        ]
        if worth
        else [],
        "risks": risks,
    }


def _security(conn, ticker: str):
    return conn.execute(
        text("SELECT id FROM securities WHERE ticker = :t"), {"t": ticker.upper()}
    ).scalar()


def practice_state(engine: Engine) -> dict:
    query = """SELECT t.id, t.created_at, s.ticker, t.side, t.shares, t.price, t.market_date,
                 t.reason, t.security_id,
                 (SELECT b.close FROM price_bars b WHERE b.security_id = t.security_id
                  ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS latest
               FROM practice_trades t JOIN securities s ON s.id = t.security_id ORDER BY t.id"""
    with engine.connect() as conn:
        trades = _rows(conn.execute(text(query)))
    cash = STARTING_CASH
    held: dict[str, dict] = {}
    for trade in trades:
        sign = 1 if trade["side"] == "buy" else -1
        cash -= sign * trade["shares"] * trade["price"]
        item = held.setdefault(trade["ticker"], {"shares": 0.0, "latest": trade["latest"]})
        item["shares"] += sign * trade["shares"]
    holdings = [
        {
            "ticker": ticker,
            "shares": item["shares"],
            "price": item["latest"],
            "worth": item["shares"] * item["latest"],
        }
        for ticker, item in held.items()
        if item["shares"] > 1e-9
    ]
    total = cash + sum(item["worth"] for item in holdings)
    return {
        "starting_cash": STARTING_CASH,
        "cash": cash,
        "holdings": holdings,
        "total": total,
        "return_percent": (total / STARTING_CASH - 1) * 100,
        "trades": list(reversed(trades))[:50],
    }


def practice_trade(
    engine: Engine, ticker: str, side: str, shares: float, reason: str
) -> str | None:
    """Trade at the latest close, against the practice balance. Returns a refusal or None."""
    state = practice_state(engine)
    with engine.begin() as conn:
        security_id = _security(conn, ticker)
        if security_id is None:
            return "This stock is not covered."
        latest = conn.execute(text(LATEST), {"id": security_id}).first()
        if latest is None:
            return "No verified price for this stock."
        if side == "buy" and shares * latest.close > state["cash"]:
            return "Not enough practice cash."
        if side == "sell":
            held = next(
                (h["shares"] for h in state["holdings"] if h["ticker"] == ticker.upper()), 0
            )
            if shares > held:
                return "You don't hold that many shares."
        conn.execute(
            text(
                """INSERT INTO practice_trades (security_id, side, shares, price, market_date, reason)
                   VALUES (:id, :side, :shares, :price, :day, :reason)"""
            ),
            {
                "id": security_id,
                "side": side,
                "shares": shares,
                "price": latest.close,
                "day": latest.market_date,
                "reason": reason,
            },
        )
    return None


def add_journal(engine: Engine, ticker: str, decision: str, reason: str) -> bool:
    with engine.begin() as conn:
        security_id = _security(conn, ticker)
        latest = (
            None if security_id is None else conn.execute(text(LATEST), {"id": security_id}).first()
        )
        if latest is None:
            return False
        conn.execute(
            text(
                """INSERT INTO journal_entries (security_id, decision, reason, price, market_date)
                   VALUES (:id, :decision, :reason, :price, :day)"""
            ),
            {
                "id": security_id,
                "decision": decision,
                "reason": reason,
                "price": latest.close,
                "day": latest.market_date,
            },
        )
    return True


def journal(engine: Engine) -> list[dict]:
    query = """SELECT j.created_at, s.ticker, j.decision, j.reason, j.price, j.market_date,
                 (SELECT b.close FROM price_bars b WHERE b.security_id = j.security_id
                  ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS latest
               FROM journal_entries j JOIN securities s ON s.id = j.security_id
               ORDER BY j.id DESC LIMIT 100"""
    with engine.connect() as conn:
        rows = _rows(conn.execute(text(query)))
    return [{**row, "change_percent": (row["latest"] / row["price"] - 1) * 100} for row in rows]


# From the SEC's Form 8-K. Serious ones can change the case for owning a stock.
EVENT_MEANINGS = {
    "1.01": ("Signed a major agreement", False),
    "1.02": ("Ended a major agreement", False),
    "1.03": ("Bankruptcy or receivership", True),
    "1.05": ("Reported a serious cybersecurity incident", True),
    "2.01": ("Completed buying or selling a large business", False),
    "2.02": ("Reported results", False),
    "2.03": ("Took on a major new debt", False),
    "2.04": ("Something made a debt come due early", True),
    "2.05": ("Started a restructuring, usually with job cuts or closures", True),
    "2.06": ("Wrote down the value of something it owns", True),
    "3.01": ("Moved its stock listing or received a notice about it", True),
    "3.02": ("Sold shares without a public offering", False),
    "3.03": ("Changed shareholders' rights", False),
    "4.01": ("Changed its auditor", True),
    "4.02": ("Said earlier accounts should no longer be relied on", True),
    "5.01": ("Control of the company changed", True),
    "5.02": ("A director or senior officer joined or left", False),
    "5.03": ("Changed its company rules or financial year", False),
    "5.07": ("Reported a shareholder vote", False),
    "7.01": ("Shared information with investors", False),
    "8.01": ("Reported other news", False),
}
SERIOUS_DAYS = 90
# These alone can change whether a company is safe to own. Others are worth a warning, since
# a restructuring, a new auditor or a move between exchanges can be routine.
SEVERE_ITEMS = ("1.03", "2.04", "4.02")
SEVERE_EVENTS = {EVENT_MEANINGS[item][0] for item in SEVERE_ITEMS}


def read_items(items: str) -> list[dict]:
    """Turn a filing's item numbers into words. Unknown numbers are left out."""
    found = []
    for item in dict.fromkeys(part.strip() for part in items.split(",")):
        if item in EVENT_MEANINGS:
            meaning, serious = EVENT_MEANINGS[item]
            found.append({"item": item, "meaning": meaning, "serious": serious})
    return found


def company_events(engine: Engine, ticker: str, today: date, days: int = 180) -> list[dict]:
    query = """SELECT e.filing_date, e.form, e.items, e.document_url, d.name AS source
               FROM filing_events e
               JOIN securities s ON s.id = e.security_id
               JOIN fetches f ON f.id = e.fetch_id
               JOIN data_sources d ON d.id = f.source_id
               WHERE s.ticker = :t AND e.filing_date >= :since
               ORDER BY e.filing_date DESC, e.id DESC LIMIT 20"""
    with engine.connect() as conn:
        rows = _rows(
            conn.execute(text(query), {"t": ticker.upper(), "since": today - timedelta(days=days)})
        )
    output = []
    for row in rows:
        events = read_items(row["items"])
        if events:
            output.append(
                {
                    "date": row["filing_date"],
                    "url": row["document_url"],
                    "source": row["source"],
                    "events": events,
                }
            )
    return output


def serious_events(events: list[dict], today: date) -> list[str]:
    return [
        item["meaning"]
        for row in events
        if (today - row["date"]).days <= SERIOUS_DAYS
        for item in row["events"]
        if item["serious"]
    ]


def alerts(engine: Engine) -> list[dict]:
    with engine.connect() as conn:
        return _rows(
            conn.execute(
                text(
                    "SELECT created_at, ticker, kind, message FROM alerts ORDER BY id DESC LIMIT 100"
                )
            )
        )


def watch(engine: Engine, ticker: str, on: bool) -> bool:
    with engine.begin() as conn:
        security_id = _security(conn, ticker)
        if security_id is None:
            return False
        if on:
            conn.execute(
                text("INSERT INTO watchlist (security_id) VALUES (:id) ON CONFLICT DO NOTHING"),
                {"id": security_id},
            )
        else:
            conn.execute(text("DELETE FROM watchlist WHERE security_id = :id"), {"id": security_id})
    return True


def watched(engine: Engine) -> list[str]:
    query = """SELECT s.ticker FROM watchlist w JOIN securities s ON s.id = w.security_id
               ORDER BY s.ticker"""
    with engine.connect() as conn:
        return list(conn.execute(text(query)).scalars())


def grade(days: int, brier: float | None, baseline: float | None) -> str:
    if days < MIN_LIVE_DAYS or brier is None or baseline is None:
        return "Too early to say"
    if brier < baseline * 0.98:
        return "Better than guessing"
    return "Worse than guessing" if brier > baseline * 1.02 else "About the same as guessing"


def shrink_factor(pairs: list[tuple[float, bool]], base: float) -> float:
    """How far to pull stated chances towards the usual rate, from 0 to 1.

    If forecasts lean twice as far from the usual rate as results justify, this is 0.5.
    """
    top = sum((chance - base) * (float(hit) - base) for chance, hit in pairs)
    bottom = sum((chance - base) ** 2 for chance, _ in pairs)
    return 1.0 if not bottom else max(0.0, min(1.0, top / bottom))


def reliability(engine: Engine) -> dict:
    base = """SELECT f.target_session, f.p_up, f.p_flat, f.p_down, s.outcome, s.brier,
                s.baseline_brier, s.in_range, c.sic
              FROM forecast_scores s JOIN forecasts f ON f.id = s.forecast_id
              JOIN securities c ON c.id = f.security_id"""
    with engine.connect() as conn:
        rows = _rows(conn.execute(text(base)))
    days = sorted({row["target_session"] for row in rows})

    def summary(items: list[dict]) -> dict:
        if not items:
            return {"count": 0, "brier": None, "baseline": None, "range_hit": None}
        count = len(items)
        return {
            "count": count,
            "brier": sum(i["brier"] for i in items) / count,
            "baseline": sum(i["baseline_brier"] for i in items) / count,
            "range_hit": sum(i["in_range"] for i in items) / count,
        }

    overall = summary(rows)
    buckets: dict[int, list] = {}
    for row in rows:
        for key, chance in (("up", row["p_up"]), ("down", row["p_down"])):
            buckets.setdefault(int(chance * 10), []).append((chance, row["outcome"] == key))
    calibration = [
        {
            "said": sum(item[0] for item in items) / len(items),
            "happened": sum(item[1] for item in items) / len(items),
            "count": len(items),
        }
        for _, items in sorted(buckets.items())
    ]
    sectors: dict[str, list] = {}
    for row in rows:
        sectors.setdefault(sector_name(row["sic"]), []).append(row)
    recent = {
        str(window): summary([r for r in rows if r["target_session"] in set(days[-window:])])
        for window in (20, 60)
    }
    return {
        "days": len(days),
        "grade": grade(len(days), overall["brier"], overall["baseline"]),
        "overall": overall,
        "calibration": calibration,
        "recent": recent,
        "sectors": [{"sector": name, **summary(items)} for name, items in sorted(sectors.items())],
    }


def warnings(report: dict) -> list[str]:
    """Plain warning signs from a company's yearly figures."""
    metrics = {item["name"]: item["value"] for item in report.get("metrics", [])}
    history = [row for row in report.get("history", []) if row["net_income"] is not None]
    found = []
    income, cash = metrics.get("Net income"), metrics.get("Operating cash flow")
    if income is not None and income < 0:
        found.append("The company made a loss in its latest year.")
    if cash is not None and cash < 0:
        found.append("The business used more cash than it brought in.")
    if income is not None and cash is not None and income > 0 and cash < income * 0.7:
        found.append("Reported profit is well above the cash the business brought in.")
    debt = metrics.get("Debt to equity")
    if debt is not None and (debt < 0 or debt > 2):
        found.append("Debt is high compared with shareholders' money.")
    if (
        len(history) >= 3
        and history[-1]["net_income"] < history[-2]["net_income"] < history[-3]["net_income"]
    ):
        found.append("Net income has fallen two years in a row.")
    return found


def next_earnings(engine: Engine, ticker: str, today: date) -> date | None:
    """An estimate: companies tend to report on a similar date each year.

    A results announcement (8-K item 2.02) is the true earnings day. The later 10-Q is the
    fallback for companies with no such history stored.
    """
    announced = """SELECT e.filing_date FROM filing_events e
                   JOIN securities s ON s.id = e.security_id
                   WHERE s.ticker = :t AND e.items LIKE '%2.02%' ORDER BY e.filing_date"""
    query = """SELECT f.filing_date FROM filings f JOIN securities s ON s.id = f.security_id
               WHERE s.ticker = :t AND f.form IN ('10-Q', '10-K') ORDER BY f.filing_date"""
    with engine.connect() as conn:
        dates = list(conn.execute(text(announced), {"t": ticker.upper()}).scalars())
        if len(dates) < 4:
            dates = list(conn.execute(text(query), {"t": ticker.upper()}).scalars())
    if not dates:
        return None
    for filed in dates:
        same_time_next_year = filed + timedelta(days=364)
        if today <= same_time_next_year <= today + timedelta(days=100):
            return same_time_next_year
    estimate = dates[-1] + timedelta(days=91)
    return estimate if estimate >= today else None


def market_mood(engine: Engine) -> dict:
    query = """SELECT DISTINCT ON (series_id) series_id, observation_date, value
               FROM economic_observations WHERE series_id IN ('VIXCLS', 'BAA10Y') AND value IS NOT NULL
               ORDER BY series_id, observation_date DESC, realtime_start DESC"""
    breadth_query = """
        WITH latest AS (SELECT max(market_date) AS day FROM price_bars),
        recent AS (
          SELECT DISTINCT ON (security_id, market_date) security_id, market_date, close
          FROM price_bars WHERE market_date >= (SELECT day FROM latest) - 300
          ORDER BY security_id, market_date, id DESC),
        ranked AS (
          SELECT security_id, close,
            avg(close) OVER (PARTITION BY security_id ORDER BY market_date
                             ROWS BETWEEN 199 PRECEDING AND CURRENT ROW) AS average,
            row_number() OVER (PARTITION BY security_id ORDER BY market_date DESC) AS position,
            count(*) OVER (PARTITION BY security_id) AS bars
          FROM recent)
        SELECT count(*) FILTER (WHERE close > average) AS above, count(*) AS total
        FROM ranked WHERE position = 1 AND bars >= 200"""
    fed = """SELECT min(decision_date) FROM fed_meetings WHERE decision_date >= current_date"""
    with engine.connect() as conn:
        latest = {row.series_id: row for row in conn.execute(text(query))}
        breadth = conn.execute(text(breadth_query)).first()
        next_fed = conn.execute(text(fed)).scalar()
    vix = latest["VIXCLS"].value if "VIXCLS" in latest else None
    if vix is None:
        mood = "Not verified"
    elif vix >= 30:
        mood = "Stressed"
    elif vix >= 20:
        mood = "Nervous"
    else:
        mood = "Calm"
    meaning = {
        "Calm": "Prices have been expected to move fairly little. Calm periods can end quickly, "
        "so keep your stops in place.",
        "Nervous": "Investors expect bigger swings than usual. Stops get hit more easily and "
        "daily moves can look alarming, so many people buy smaller amounts in these periods.",
        "Stressed": "Investors expect very large swings. Losses can build quickly and prices can "
        "jump past your stop, so this is a poor time to risk more than you planned.",
        "Not verified": "The latest reading isn't available, so don't rely on this.",
    }[mood]
    return {
        "mood": mood,
        "meaning": meaning,
        "vix": vix,
        "credit_spread": latest["BAA10Y"].value if "BAA10Y" in latest else None,
        "above_200": breadth.above / breadth.total if breadth and breadth.total else None,
        "stocks_measured": breadth.total if breadth else 0,
        "next_fed": next_fed,
    }
