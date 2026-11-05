"""The big picture: readings from official sources, and what each means for a buyer.

Nothing here is a forecast. Each card states a stored reading and links to its source.
"""

from datetime import date, timedelta

from sqlalchemy import Engine, text

from stockintel import calendar_events

FRED = "https://fred.stlouisfed.org/series/"
GOOD, BAD, NEUTRAL, UNKNOWN = "good", "bad", "neutral", "unknown"
MAX_AGE = timedelta(days=14)
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
        "cards": [
            curve(ten, two, short, day),
            rates(funds, before, funds_day),
            uncertainty(recent, usual, policy_day),
            elections(today),
        ],
        "actions": [dict(row._mapping) for row in actions],
    }
