"""The big picture: readings from official sources, and what each means for a buyer.

Nothing here is a forecast. Each card states a stored reading and links to its source.
"""

from datetime import date, timedelta

from sqlalchemy import Engine, text

from stockintel import calendar_events, news_judge, news_watch
from stockintel.providers.news import INDUSTRIES, TOPICS, industry_of

FRED = "https://fred.stlouisfed.org/series/"
GOOD, BAD, NEUTRAL, UNKNOWN = "good", "bad", "neutral", "unknown"
MAX_AGE = timedelta(days=14)
MARKETS = {"SPY": "S&P 500", "QQQ": "Nasdaq 100", "DIA": "Dow Jones"}
NEWS_DAYS = 7
TONE_GAP = 0.3
SERIES = ("DGS2", "DGS10", "T10Y3M", "DFF", "USEPUINDXD")


def card(title, reading, state, meaning, source, url, day=None):
    return {
        "title": title,
        "reading": reading,
        "state": state,
        "meaning": meaning,
        "source": source,
        "url": url,
        "date": day,
    }


def curve(ten, two, three_month, day) -> dict:
    title, source, url = "Yield curve", "Federal Reserve, via FRED", f"{FRED}T10Y3M"
    if ten is None or two is None:
        return card(title, "Not verified", UNKNOWN, "The latest reading is missing.", source, url)
    gap = ten - two
    reading = f"10-year minus 2-year: {gap:+.2f}%"
    if three_month is not None:
        reading += f". 10-year minus 3-month: {three_month:+.2f}%"
    inverted = gap < 0 or (three_month is not None and three_month < 0)
    if inverted:
        meaning = (
            "Short-term loans pay more than long-term ones. This has often come before US "
            "recessions, but usually many months ahead, so it's a warning and not a sell signal."
        )
        return card(title, reading, BAD, meaning, source, url, day)
    meaning = (
        "Long-term loans pay more than short-term ones, which is the normal shape. "
        "It gives no recession warning at the moment."
    )
    return card(title, reading, GOOD, meaning, source, url, day)


def rates(now, before, day) -> dict:
    title, source, url = "Interest rates", "Federal Reserve, via FRED", f"{FRED}DFF"
    if now is None:
        return card(title, "Not verified", UNKNOWN, "The latest reading is missing.", source, url)
    reading = f"Fed funds rate: {now:.2f}%"
    if before is None:
        return card(title, reading, NEUTRAL, "No earlier reading to compare.", source, url, day)
    change = now - before
    reading += f", {change:+.2f} points in 60 days"
    if change <= -0.1:
        meaning = "The Fed has been cutting, which makes borrowing cheaper for firms and buyers."
        return card(title, reading, GOOD, meaning, source, url, day)
    if change >= 0.1:
        meaning = "The Fed has been raising rates, which makes borrowing dearer and can weigh on "
        meaning += "stocks whose profits are far in the future."
        return card(title, reading, BAD, meaning, source, url, day)
    meaning = "The Fed has held rates steady, so check the next decision date."
    return card(title, reading, NEUTRAL, meaning, source, url, day)


def uncertainty(recent, usual, day) -> dict:
    title = "Government policy uncertainty"
    source, url = "Baker, Bloom and Davis, via FRED", f"{FRED}USEPUINDXD"
    if recent is None or usual is None:
        return card(title, "Not verified", UNKNOWN, "The latest reading is missing.", source, url)
    reading = f"30-day average {recent:.0f}, against a usual {usual:.0f}"
    if recent >= usual * 1.5:
        meaning = (
            "News is unusually full of uncertainty over government policy. "
            "Expect bigger swings when policy decisions land."
        )
        return card(title, reading, BAD, meaning, source, url, day)
    meaning = "News about government policy is close to its usual level of uncertainty."
    return card(title, reading, NEUTRAL, meaning, source, url, day)


def elections(today: date) -> dict:
    title = "US elections"
    url = "https://www.usa.gov/election-day"
    day, kind = calendar_events.next_election(today)
    window = calendar_events.election_window(today)
    last = calendar_events.election_day(today.year if today.year % 2 == 0 else today.year - 1)
    if window == 1:
        reading = f"{(today - last).days} days after the vote on {last}"
    else:
        reading = f"Next: {kind} on {day}"
    meaning = (
        "Policy expectations can shift around a vote, and some industries gain or lose more than "
        "others. Only a few elections are in this app's data, so no election pattern can be proven."
    )
    return card(title, reading, NEUTRAL, meaning, "US federal election law", url, last)


def tone_word(recent: float | None, usual: float | None) -> str:
    if recent is None or usual is None:
        return "Not verified"
    if recent <= usual - TONE_GAP:
        return "More negative than usual"
    if recent >= usual + TONE_GAP:
        return "More positive than usual"
    return "About usual"


def headlines(engine: Engine, subject: str, today: date, count: int = 5) -> dict:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT title, url, domain, seen_at FROM news_articles
                   WHERE subject = :s AND seen_at >= :since
                   ORDER BY seen_at DESC LIMIT :count"""
            ),
            {"s": subject, "since": today - timedelta(days=NEWS_DAYS), "count": count},
        ).all()
        tones = (
            conn.execute(
                text("SELECT tone FROM news_tone WHERE subject = :s ORDER BY day DESC LIMIT 30"),
                {"s": subject},
            )
            .scalars()
            .all()
        )
    recent = sum(tones[:3]) / len(tones[:3]) if tones else None
    usual = sum(tones) / len(tones) if len(tones) >= 7 else None
    return {
        "subject": subject,
        "tone": tone_word(recent, usual),
        "articles": [dict(row._mapping) for row in rows],
    }


def news(engine: Engine, today: date) -> dict:
    """Headlines sorted by how far they reach: everything, one industry, or one company."""
    whole = [
        headlines(engine, subject, today, 3) for subject in (*TOPICS, "Official announcements")
    ]
    sectors = [headlines(engine, f"Industry: {name}", today, 3) for name in INDUSTRIES]
    query = """SELECT n.subject, s.name, n.title, n.url, n.domain, n.seen_at
               FROM news_articles n JOIN securities s ON s.ticker = n.subject
               WHERE n.seen_at >= :since ORDER BY n.seen_at DESC LIMIT 40"""
    with engine.connect() as conn:
        rows = conn.execute(text(query), {"since": today - timedelta(days=2)}).all()
    return {
        "market": [group for group in whole if group["articles"]],
        "industries": [
            {**group, "subject": group["subject"].removeprefix("Industry: ")}
            for group in sectors
            if group["articles"]
        ],
        "companies": [dict(row._mapping) for row in rows],
    }


def stock_news(engine: Engine, ticker: str, today: date) -> dict:
    """News naming a company, plus news on its industry and the whole market."""
    with engine.connect() as conn:
        sic = conn.execute(
            text("SELECT sic FROM securities WHERE ticker = :t"), {"t": ticker}
        ).scalar()
    own = headlines(engine, ticker, today, 8)
    subject = industry_of(sic)
    group = headlines(engine, subject, today, 5) if subject else None
    return {
        **own,
        "industry": None
        if group is None
        else {**group, "subject": subject.removeprefix("Industry: ")},
        "market": [
            item for item in news(engine, today)["market"] if item["tone"] != "Not verified"
        ][:2],
    }


def market_trend(engine: Engine) -> dict | None:
    query = """SELECT value FROM (SELECT DISTINCT ON (observation_date) observation_date, value
                 FROM economic_observations WHERE series_id = 'SP500' AND value IS NOT NULL
                 ORDER BY observation_date DESC, realtime_start DESC LIMIT 200) AS recent
               ORDER BY observation_date"""
    with engine.connect() as conn:
        values = list(conn.execute(text(query)).scalars())
    if len(values) < 200:
        return None
    return {
        "above_200": values[-1] > sum(values) / len(values),
        "month": values[-1] / values[-21] - 1,
    }


def market_note(engine: Engine) -> str:
    """One line on the whole market, shown beside every stock's decision."""
    strip = market_strip(engine)["markets"][0]
    trend = market_trend(engine)
    if strip["change"] is None and trend is None:
        return "Whole market: Not verified."
    parts = []
    if strip["change"] is not None:
        parts.append(f"The S&P 500 is {strip['change'] * 100:+.2f}% on the day")
    if trend:
        side = "above" if trend["above_200"] else "below"
        parts.append(
            f"{trend['month'] * 100:+.1f}% over 20 trading days and {side} its 200-day average"
        )
    return "Whole market: " + ", ".join(parts) + ". Most stocks move with the market."


def market_strip(engine: Engine) -> dict:
    """Where the main US markets stand, and how holdings compare with the S&P 500."""
    latest = """SELECT DISTINCT ON (ticker) ticker, quoted_at, price, previous_close
                FROM market_quotes ORDER BY ticker, quoted_at DESC"""
    index = """SELECT DISTINCT ON (observation_date) observation_date, value
               FROM economic_observations
               WHERE series_id = 'SP500' AND value IS NOT NULL AND observation_date >= :since
               ORDER BY observation_date, realtime_start DESC"""
    holdings = """SELECT p.shares, p.buy_price, p.updated_at::date AS since,
                    (SELECT b.close FROM price_bars b WHERE b.security_id = p.security_id
                     ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS price
                  FROM positions p"""
    with engine.connect() as conn:
        quotes = {row.ticker: row for row in conn.execute(text(latest))}
        owned = [row for row in conn.execute(text(holdings)) if row.price]
        since = min((row.since for row in owned), default=None)
        points = conn.execute(text(index), {"since": since}).all() if since else []
    markets = []
    for ticker, name in MARKETS.items():
        row = quotes.get(ticker)
        markets.append(
            {
                "name": name,
                "ticker": ticker,
                "price": None if row is None else row.price,
                "change": None if row is None else row.price / row.previous_close - 1,
                "at": None if row is None else row.quoted_at,
            }
        )
    versus = None
    if owned and len(points) >= 2:
        cost = sum(row.shares * row.buy_price for row in owned)
        worth = sum(row.shares * row.price for row in owned)
        versus = {
            "since": points[0].observation_date,
            "yours": worth / cost - 1,
            "market": points[-1].value / points[0].value - 1,
        }
    return {"markets": markets, "versus": versus}


def build(engine: Engine, today: date) -> dict:
    query = """SELECT DISTINCT ON (series_id, observation_date) series_id, observation_date, value
               FROM economic_observations
               WHERE series_id IN :ids AND observation_date >= :since AND value IS NOT NULL
               ORDER BY series_id, observation_date, realtime_start DESC"""
    from sqlalchemy import bindparam

    with engine.connect() as conn:
        rows = conn.execute(
            text(query).bindparams(bindparam("ids", expanding=True)),
            {"ids": list(SERIES), "since": today - timedelta(days=1900)},
        ).all()
        actions = conn.execute(
            text(
                """SELECT published, kind, title, topic, url FROM policy_documents
                   WHERE published >= :since AND (topic IS NOT NULL OR kind = 'Executive Order')
                   ORDER BY published DESC, document_number DESC LIMIT 12"""
            ),
            {"since": today - timedelta(days=60)},
        ).all()
    by_series: dict = {}
    for row in rows:
        by_series.setdefault(row.series_id, []).append((row.observation_date, row.value))

    def fresh(series):
        items = by_series.get(series, [])
        if not items or today - items[-1][0] > MAX_AGE:
            return None, None
        return items[-1][1], items[-1][0]

    ten, day = fresh("DGS10")
    two, _ = fresh("DGS2")
    short, _ = fresh("T10Y3M")
    funds, funds_day = fresh("DFF")
    before = None
    if funds_day:
        older = [v for d, v in by_series["DFF"] if d <= funds_day - timedelta(days=60)]
        before = older[-1] if older else None
    policy = by_series.get("USEPUINDXD", [])
    recent = usual = policy_day = None
    if fresh("USEPUINDXD")[0] is not None and len(policy) >= 365:
        values = sorted(value for _, value in policy)
        recent = sum(value for _, value in policy[-30:]) / 30
        usual = values[len(values) // 2]
        policy_day = policy[-1][0]
    return {
        "news": news(engine, today),
        "warnings": news_watch.summary(engine, today),
        "judged": news_judge.recent(engine, today),
        "cards": [
            curve(ten, two, short, day),
            rates(funds, before, funds_day),
            uncertainty(recent, usual, policy_day),
            elections(today),
        ],
        "actions": [dict(row._mapping) for row in actions],
    }
