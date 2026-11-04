"""Check every company's figures for signs of a wrong reading.

These are consistency checks. They catch impossible or out-of-date figures. They can't
prove a figure is right, because that needs a second independent source.

Run: python -m stockintel.audit
"""

from collections import Counter
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import longterm, queries
from stockintel.db import get_engine

MAX_AGE = timedelta(days=500)


def check(report: dict, today: date) -> list[str]:
    """Plain-English problems with a company's report. Empty means none were found."""
    metrics = {item["name"]: item for item in report.get("metrics", [])}

    def value(name):
        return metrics[name]["value"] if name in metrics else None

    def latest_period(name):
        sources = metrics[name]["sources"] if name in metrics else []
        return max((item["period_end"] for item in sources), default=None)

    problems = []
    if not report.get("available"):
        return ["No company figures are stored."]
    revenue, income = value("Revenue"), value("Net income")
    gross = value("Gross profit")
    if revenue is None:
        problems.append("Revenue could not be found.")
    if income is None:
        problems.append("Net income could not be found.")
    newest = [
        period
        for period in (latest_period("Revenue"), latest_period("Net income"))
        if period is not None
    ]
    if newest and today - max(newest) > MAX_AGE:
        problems.append("The latest yearly figures are over 500 days old.")
    if len(set(newest)) == 2:
        problems.append("Revenue and net income come from different years.")
    # Zero is real for a drug developer with nothing on sale yet. Negative never is.
    if revenue is not None and revenue < 0:
        problems.append("Revenue is negative.")
    margin = value("Gross margin")
    if margin is not None and not -1 <= margin <= 1:
        problems.append("Gross margin is outside what is possible.")
    same_year = latest_period("Gross profit") == latest_period("Revenue")
    if gross is not None and revenue is not None and same_year and gross > revenue:
        problems.append("Gross profit is larger than revenue.")
    same_year = latest_period("Net income") == latest_period("Revenue")
    # Large losses happen, such as a fall in the value of holdings. Such profits rarely do.
    if (
        income is not None
        and revenue is not None
        and revenue > 0
        and same_year
        and (income > revenue * 3)
    ):
        problems.append("Net income is unusually large compared with revenue.")
    return problems


def run(engine: Engine) -> dict:
    today = datetime.now(UTC).date()
    query = """SELECT s.id, s.ticker, (SELECT b.close FROM price_bars b
                 WHERE b.security_id = s.id ORDER BY b.market_date DESC, b.id DESC LIMIT 1) AS price
               FROM securities s ORDER BY s.universe_rank"""
    with engine.connect() as conn:
        securities = conn.execute(text(query)).all()
    tally: Counter = Counter()
    flagged = {}
    for security in securities:
        facts = queries.load_facts(engine, security.id)
        report = longterm.report(facts, security.price)
        problems = check(report, today)
        if problems:
            flagged[security.ticker] = problems
        tally.update(problems)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM validation_issues WHERE feed = 'audit'"))
        rows = [
            {"ticker": ticker, "detail": problem}
            for ticker, problems in flagged.items()
            for problem in problems
        ]
        if rows:
            conn.execute(
                text(
                    """INSERT INTO validation_issues (feed, kind, ticker, detail)
                       VALUES ('audit', 'invalid', :ticker, :detail)"""
                ),
                rows,
            )
    print("checked", len(securities), "flagged", len(flagged))
    for problem, count in tally.most_common():
        names = [ticker for ticker, items in flagged.items() if problem in items][:12]
        print(count, problem, names)
    return {"checked": len(securities), "flagged": flagged}


if __name__ == "__main__":
    pd.options.mode.copy_on_write = True
    run(get_engine())
