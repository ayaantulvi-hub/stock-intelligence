"""Bad news reaching decisions, through a plain safety rule.

Several negative headlines from different outlets on one company or industry stop a buy and
flag anything you own. This reads words, not meaning, so it can be wrong, and it only ever
makes the app more careful. It isn't proven. Each warning is stored so it can be tested.
"""

from datetime import date, timedelta

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import news_judge
from stockintel.providers.news import TOPIC_INDUSTRIES, headline_mood, industry_of

WINDOW_DAYS = 2
MIN_BAD = 3
MIN_OUTLETS = 2


def assess(rows: list[dict]) -> dict | None:
    """A warning if bad headlines outnumber good ones two to one, across two outlets."""
    moods = [(row, headline_mood(row["title"])) for row in rows]
    bad = [row for row, mood in moods if mood < 0]
    good = sum(mood > 0 for _, mood in moods)
    outlets = {row["domain"] for row in bad}
    if len(bad) < MIN_BAD or len(outlets) < MIN_OUTLETS or len(bad) < good * 2:
        return None
    latest = max(bad, key=lambda row: row["seen_at"])
    return {
        "bad": len(bad),
        "outlets": len(outlets),
        "title": latest["title"],
        "url": latest["url"],
        "domain": latest["domain"],
    }


def warnings(engine: Engine, today: date) -> dict[str, dict]:
    """Current warnings by subject, a ticker or an industry."""
    query = """SELECT subject, title, url, domain, seen_at FROM news_articles
               WHERE seen_at >= :since"""
    with engine.connect() as conn:
        rows = [
            dict(row._mapping)
            for row in conn.execute(text(query), {"since": today - timedelta(days=WINDOW_DAYS)})
        ]
    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["subject"], []).append(row)
    found = {subject: assess(items) for subject, items in groups.items()}
    found = {subject: value for subject, value in found.items() if value}
    # An AI reading of a big story counts on its own, because one story can be enough.
    for item in news_judge.recent(engine, today, ("big",)):
        if item["effect"] != "negative":
            continue
        warning = {
            "bad": 1,
            "outlets": 1,
            "title": item["title"],
            "url": item["url"],
            "domain": item["domain"],
            "why": item["why"],
        }
        targets = [f"Industry: {name}" for name in item["industries"]] + list(item["tickers"])
        if item["scope"] == "market":
            targets.append("Whole market")
        for subject in targets:
            found.setdefault(subject, warning)
    # A story on a broad theme reaches the industries inside it.
    for topic, industries in TOPIC_INDUSTRIES.items():
        if topic in found:
            for industry in industries:
                found.setdefault(industry, found[topic])
    return found


def reason(subject: str, warning: dict) -> str:
    name = subject.replace("Industry: ", "the ") + (" industry" if "Industry" in subject else "")
    if warning.get("why"):
        return f'of news on {name}: {warning["why"]} ("{warning["title"]}", {warning["domain"]})'
    return (
        f"of bad news on {name}: {warning['bad']} negative headlines from "
        f'{warning["outlets"]} outlets, such as "{warning["title"]}" ({warning["domain"]})'
    )


def stock_warnings(engine: Engine, today: date) -> dict[str, str]:
    """The reason to be careful with each affected stock."""
    found = warnings(engine, today)
    if not found:
        return {}
    with engine.connect() as conn:
        stocks = conn.execute(text("SELECT ticker, sic FROM securities")).all()
    output = {}
    for ticker, sic in stocks:
        subject = ticker if ticker in found else industry_of(sic)
        if subject in found:
            output[ticker] = reason(subject, found[subject])
    return output


def record(engine: Engine, today: date) -> int:
    """Keep each day's warnings, so whether they helped can be measured later."""
    found = warnings(engine, today)
    with engine.begin() as conn:
        for subject, warning in found.items():
            conn.execute(
                text(
                    """INSERT INTO news_warnings (day, subject, bad, outlets, title, url)
                       VALUES (:day, :subject, :bad, :outlets, :title, :url)
                       ON CONFLICT (day, subject) DO NOTHING"""
                ),
                {
                    "day": today,
                    "subject": subject,
                    "bad": warning["bad"],
                    "outlets": warning["outlets"],
                    "title": warning["title"],
                    "url": warning["url"],
                },
            )
    return len(found)


def summary(engine: Engine, today: date) -> list[dict]:
    found = warnings(engine, today)
    frame = pd.DataFrame(
        [{"subject": key.replace("Industry: ", ""), **value} for key, value in found.items()]
    )
    return [] if frame.empty else frame.sort_values("bad", ascending=False).to_dict("records")
