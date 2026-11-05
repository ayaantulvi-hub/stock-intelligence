"""An expert review: well-known investing methods applied as written rules.

Each lens follows a published method and uses stored, sourced figures only. A lens that lacks
a figure says Not verified rather than guessing. These are rules, not an opinion from any
named investor, and most have not been proven in this app. Only the Piotroski score is
tested here, as a model factor.

Run after the daily data: python -m stockintel.experts
"""

import json
import sys
from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import Engine, text

from stockintel import candles, context, horizons, localcache, longterm, tools
from stockintel.charts import fibonacci, sma
from stockintel.db import get_engine

GOOD, BAD, MIXED, UNKNOWN = "good", "bad", "mixed", "unknown"
F_STRONG, F_WEAK = 7, 2
Z_NEEDS_HEALTH = 4
Z_SAFE, Z_DISTRESS = 2.99, 1.81
GRAHAM_LIMIT = 22.5
SURGE = 0.25
TRADING_YEAR = 252


def lens(name: str, source: str, verdict: str, reason: str, teaches: str) -> dict:
    return {
        "name": name,
        "source": source,
        "verdict": verdict,
        "reason": reason,
        "teaches": teaches,
    }


def _metrics(report: dict) -> dict:
    return {item["name"]: item["value"] for item in report.get("metrics", [])}


def piotroski(facts: pd.DataFrame) -> dict:
    name, source = "Is the business getting healthier?", "Piotroski (2000)"
    teaches = "Nine yes-or-no tests of profit, debt and efficiency against last year."
    table = longterm.fscore_table(facts)
    if table.empty or pd.isna(table["fscore"].iloc[-1]):
        return lens(name, source, UNKNOWN, "Not verified: too few figures to score.", teaches)
    row = table.iloc[-1]
    score, tests = int(row["fscore"]), int(row["tests"])
    verdict = GOOD if score >= F_STRONG else BAD if score <= F_WEAK else MIXED
    return {
        **lens(name, source, verdict, f"Scores {score} of {tests} health tests.", teaches),
        "score": score,
    }


def altman(facts: pd.DataFrame, market_value: float | None, sic: int | None) -> dict:
    name, source = "Could it go bust?", "Altman (1968)"
    teaches = "A formula from company accounts that separated failing firms from healthy ones."
    if sic is not None and (6000 <= sic <= 6999 or 4900 <= sic <= 4999):
        return lens(
            name,
            source,
            UNKNOWN,
            "Not verified: the formula doesn't suit banks or utilities.",
            teaches,
        )
    value = longterm.altman_z(facts, market_value)
    if value is None:
        return lens(name, source, UNKNOWN, "Not verified: a figure it needs is missing.", teaches)
    if value >= Z_SAFE:
        return {**lens(name, source, GOOD, f"Safe zone, score {value:.1f}.", teaches), "z": value}
    if value < Z_DISTRESS:
        return {
            **lens(name, source, BAD, f"Danger zone, score {value:.1f}.", teaches),
            "z": value,
        }
    return {**lens(name, source, MIXED, f"Grey zone, score {value:.1f}.", teaches), "z": value}


def graham(report: dict, market_value: float | None) -> dict:
    name, source = "Is it cheap?", "Graham, The Intelligent Investor"
    teaches = "Price against profit, times price against net assets, should be 22.5 or less."
    figures = _metrics(report)
    income = figures.get("Net income")
    equity = report.get("equity")
    if not market_value or income is None or not equity:
        return lens(name, source, UNKNOWN, "Not verified: a figure it needs is missing.", teaches)
    if income <= 0 or equity <= 0:
        return lens(name, source, BAD, "No profit or net assets to pay for.", teaches)
    number = (market_value / income) * (market_value / equity)
    verdict = GOOD if number <= GRAHAM_LIMIT else BAD if number > GRAHAM_LIMIT * 4 else MIXED
    return lens(name, source, verdict, f"Scores {number:.0f}, against his limit of 22.5.", teaches)


def quality(report: dict) -> dict:
    name, source = "Is it a good business?", "Buffett's letters, as commonly summarised"
    teaches = "High returns, steady profits, little debt and real cash."
    figures = _metrics(report)
    history = [row["net_income"] for row in report.get("history", [])]
    tests = {
        "high return on shareholders' money": (
            None if figures.get("Return on equity") is None else figures["Return on equity"] >= 0.15
        ),
        "good profit margin": (
            None
            if figures.get("Net profit margin") is None
            else figures["Net profit margin"] >= 0.10
        ),
        "little debt": (
            None if figures.get("Debt to equity") is None else 0 <= figures["Debt to equity"] <= 0.5
        ),
        "brings in cash": (
            None if figures.get("Free cash flow") is None else figures["Free cash flow"] > 0
        ),
        "no recent losses": (
            None if len(history) < 3 or any(item is None for item in history) else min(history) > 0
        ),
    }
    known = {key: value for key, value in tests.items() if value is not None}
    if len(known) < 3:
        return lens(name, source, UNKNOWN, "Not verified: too few figures.", teaches)
    passed, failed = [k for k, v in known.items() if v], [k for k, v in known.items() if not v]
    verdict = GOOD if len(failed) <= 1 else BAD if len(passed) <= 1 else MIXED
    reason = f"Passes {len(passed)} of {len(known)}."
    if failed:
        reason += " Falls short on: " + ", ".join(failed) + "."
    return lens(name, source, verdict, reason, teaches)


def safety(report: dict) -> dict:
    name, source = "Is there room for error?", "Graham's margin of safety"
    teaches = "Pay well under your estimate of value, because estimates are often wrong."
    cases = {case["name"]: case for case in report.get("cases", [])}
    if "Base" not in cases:
        return lens(name, source, UNKNOWN, "Not verified: no value estimate.", teaches)
    gap = cases["Base"]["against_price"]
    verdict = GOOD if gap >= 0.15 else BAD if gap < -0.3 else MIXED
    return lens(
        name, source, verdict, f"Base value is {gap * 100:+.0f}% against the price.", teaches
    )


def trend(frame: pd.DataFrame) -> dict:
    name, source = "Is the price trend healthy?", "Weinstein and Minervini's trend rules"
    teaches = "Traders want a rising long-term average and a price near its highs."
    if len(frame) < TRADING_YEAR:
        return lens(name, source, UNKNOWN, "Not verified: under a year of prices.", teaches)
    close = frame["close"]
    price = float(close.iloc[-1])
    long_average = sma(close, 200)
    year = close.iloc[-TRADING_YEAR:]
    tests = [
        price > sma(close, 150).iloc[-1],
        price > long_average.iloc[-1],
        long_average.iloc[-1] > long_average.iloc[-22],
        sma(close, 50).iloc[-1] > sma(close, 150).iloc[-1],
        price >= year.max() * 0.75,
        price >= year.min() * 1.3,
    ]
    passed = sum(bool(test) for test in tests)
    verdict = GOOD if passed == 6 else BAD if passed <= 2 else MIXED
    return lens(name, source, verdict, f"Meets {passed} of 6 trend rules.", teaches)


def fibonacci_lens(frame: pd.DataFrame) -> dict:
    name, source = "Where is it on the Fibonacci levels?", "Fibonacci retracements, a trader rule"
    teaches = "After a big move, traders watch 38.2%, 50% and 61.8% pullbacks for a turn."
    found = fibonacci(frame) if len(frame) >= 30 and "high" in frame else None
    if not found:
        return lens(name, source, UNKNOWN, "Not verified: too little history.", teaches)
    if not found["rising"]:
        near = found["near"]
        spot = (
            f" It's near the {near['ratio'] * 100:.1f}% level at {near['price']:.2f}."
            if near
            else ""
        )
        return lens(name, source, MIXED, f"Its last big move was down.{spot}", teaches)
    pullback = found["pullback"]
    words = f"It has given back {pullback * 100:.0f}% of its last big rise"
    if pullback > 0.786:
        return lens(name, source, BAD, f"{words}, past the 78.6% level.", teaches)
    if 0.3 <= pullback <= 0.7:
        return lens(name, source, GOOD, f"{words}, inside the usual pullback zone.", teaches)
    return lens(name, source, MIXED, f"{words}.", teaches)


def market_lens(market: dict | None) -> dict:
    name, source = "Is the whole market healthy?", "S&P 500 from FRED"
    teaches = "Most stocks fall when the market does, so traders check it first."
    if not market:
        return lens(name, source, UNKNOWN, "Not verified: no market reading.", teaches)
    above = market["above_200"]
    words = f"S&P 500 is {'above' if above else 'below'} its 200-day average"
    words += f" and {market['month'] * 100:+.1f}% over 20 trading days."
    return lens(
        name,
        source,
        GOOD if above and market["month"] >= 0 else BAD if not above else MIXED,
        words,
        teaches,
    )


def filings_lens(serious: list[str]) -> dict:
    name, source = "Any trouble in its filings?", "SEC Form 8-K"
    teaches = "Experienced investors read what a company must report before trusting the numbers."
    if serious:
        severe = any(event in tools.SEVERE_EVENTS for event in serious)
        return {**lens(name, source, BAD, "; ".join(serious) + ".", teaches), "severe": severe}
    return lens(name, source, GOOD, "Nothing serious in the last 90 days.", teaches)


def mental_traps(
    frame: pd.DataFrame, position: dict | None, earnings_in: int | None, outside: dict | None
) -> list[dict]:
    """Known decision mistakes that apply to this stock today."""
    traps = []

    def trap(name, source, text_):
        traps.append({"name": name, "source": source, "text": text_})

    if len(frame) > 21:
        move = float(frame["close"].iloc[-1] / frame["close"].iloc[-21] - 1)
        if move >= SURGE:
            trap(
                "Chasing a jump",
                "De Bondt & Thaler (1985)",
                f"It rose {move * 100:.0f}% in a month. People tend to overreact to recent news.",
            )
        elif move <= -SURGE:
            trap(
                "Anchoring on the old price",
                "Tversky & Kahneman (1974)",
                f"It fell {-move * 100:.0f}% in a month. It isn't cheap just because it was "
                "higher before. Find out why it fell.",
            )
    if position and position.get("profit") is not None:
        percent = position["profit"] / (position["shares"] * position["buy_price"])
        if percent <= -0.1:
            trap(
                "Holding a loser to avoid admitting it",
                "Shefrin & Statman (1985), Odean (1998)",
                "People hold losers too long. Ask: would I buy it today at this price?",
            )
        elif percent >= 0.2:
            trap(
                "Selling a winner too early",
                "Shefrin & Statman (1985), Odean (1998)",
                "People sell winners too soon. Sell for a reason, not just to bank the gain.",
            )
    if earnings_in is not None and 0 <= earnings_in <= 7:
        trap(
            "Betting into results",
            "Kahneman, Thinking, Fast and Slow",
            f"Results are expected in about {earnings_in} days. A big move either way is "
            "close to a coin toss, however sure you feel.",
        )
    if outside:
        trap(
            "Forgetting the usual outcome",
            "Kahneman & Lovallo (1993)",
            f"Across {outside['trades']:,} past test trades held 20 days, "
            f"{outside['win_rate'] * 100:.0f}% made money and the worst lost "
            f"{-outside['worst_return'] * 100:.0f}%. Expect something like that, not the best case.",
        )
    return traps


def block_reason(lenses: list[dict]) -> str | None:
    """A rule that overrides a buy. Each is a sign of serious trouble, not a matter of taste."""
    health = next((item["score"] for item in lenses if "score" in item), None)
    for item in lenses:
        if item["verdict"] != BAD:
            continue
        # Debt-funded finance arms can trip this score alone, so weak health must agree.
        if "z" in item and health is not None and health <= Z_NEEDS_HEALTH:
            return f"its accounts are in Altman's danger zone and its health score is {health}"
        if "score" in item and item["score"] <= F_WEAK:
            return f"it fails most business health tests ({item['reason']})"
        if item.get("severe"):
            return f"of a serious filing: {item['reason']}"
    return None


def review(
    facts: pd.DataFrame,
    report: dict,
    frame: pd.DataFrame,
    *,
    sic: int | None,
    serious: list[str],
    position: dict | None = None,
    earnings_in: int | None = None,
    outside: dict | None = None,
    market: dict | None = None,
) -> dict:
    price, shares = report.get("price"), None
    if not facts.empty and not report.get("receipts") and report.get("currency") == "USD":
        rows = facts[facts["tag"] == "EntityCommonStockSharesOutstanding"]
        shares = None if rows.empty else float(rows.sort_values("filed").iloc[-1]["value"])
    market_value = price * shares if price and shares else None
    lenses = [
        piotroski(facts),
        altman(facts, market_value, sic),
        quality(report),
        graham(report, market_value),
        safety(report),
        trend(frame),
        fibonacci_lens(frame),
        market_lens(market),
        filings_lens(serious),
    ]
    return {
        "lenses": lenses,
        "agree": sum(item["verdict"] == GOOD for item in lenses),
        "against": sum(item["verdict"] == BAD for item in lenses),
        "unknown": sum(item["verdict"] == UNKNOWN for item in lenses),
        "blocked": block_reason(lenses),
        "traps": mental_traps(frame, position, earnings_in, outside),
    }


def load_outside(engine: Engine) -> dict | None:
    query = """SELECT trades, win_rate, worst_return FROM stop_studies
               WHERE stop_multiple IS NULL AND run_at = (SELECT max(run_at) FROM stop_studies)"""
    with engine.connect() as conn:
        row = conn.execute(text(query)).first()
    return None if row is None else dict(row._mapping)


def stored_trades(engine: Engine) -> list[dict]:
    """Today's short-term signals across all stocks, tested ones first."""
    query = """SELECT DISTINCT ON (s.ticker) s.ticker, s.name, r.short_term, r.review_date
               FROM expert_reviews r JOIN securities s ON s.id = r.security_id
               WHERE r.short_term IS NOT NULL ORDER BY s.ticker, r.id DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    found = [
        {"ticker": row.ticker, "name": row.name, "date": row.review_date, **row.short_term}
        for row in rows
        if row.short_term["kind"] != "neutral"
    ]
    return sorted(found, key=lambda item: (not item["proven"], item["ticker"]))


def stored_investments(engine: Engine) -> list[dict]:
    """Stocks whose company checks make them long-term buys, strongest first."""
    query = """SELECT DISTINCT ON (s.ticker) s.ticker, s.name, r.detail, r.blocked, r.agree,
                 r.against
               FROM expert_reviews r JOIN securities s ON s.id = r.security_id
               ORDER BY s.ticker, r.id DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    found = []
    for row in rows:
        view = horizons.invest({"lenses": row.detail, "blocked": row.blocked})
        if view["kind"] == "buy":
            found.append(
                {
                    "ticker": row.ticker,
                    "name": row.name,
                    "score": row.agree - row.against,
                    **view,
                }
            )
    return sorted(found, key=lambda item: (-item["score"], item["ticker"]))


def stored_blocks(engine: Engine) -> dict[str, str]:
    query = """SELECT DISTINCT ON (s.ticker) s.ticker, r.blocked
               FROM expert_reviews r JOIN securities s ON s.id = r.security_id
               ORDER BY s.ticker, r.id DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    return {row.ticker: row.blocked for row in rows if row.blocked}


def run(engine: Engine) -> int:
    """Review every stock, so the home page lists match each stock's own page."""
    from stockintel.charts import adjust

    today: date = datetime.now(UTC).date()
    with engine.connect() as conn:
        securities = conn.execute(
            text("SELECT id, ticker, sic FROM securities ORDER BY universe_rank")
        ).all()
    bars = localcache.daily_bars(engine)
    all_facts = localcache.facts_by_security(engine)
    outside = load_outside(engine)
    market = context.market_trend(engine)
    candle_tests = candles.latest_tests(engine)
    done = 0
    for security in securities:
        raw = bars.get(security.id)
        if raw is None or raw.empty:
            continue
        ticker = security.ticker
        facts = all_facts.get(security.id, pd.DataFrame())
        earnings = tools.next_earnings(engine, ticker, today)
        result = review(
            facts,
            longterm.report(facts, float(raw["close"].iloc[-1])),
            adjust(raw),
            sic=security.sic,
            serious=tools.serious_events(tools.company_events(engine, ticker, today), today),
            earnings_in=(earnings - today).days if earnings else None,
            outside=outside,
            market=market,
        )
        short = horizons.trade(
            adjust(raw),
            candle_tests,
            False,
            (earnings - today).days if earnings else None,
        )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """INSERT INTO expert_reviews (security_id, review_date, agree, against,
                         blocked, detail, short_term)
                       SELECT id, :day, :agree, :against, :blocked, CAST(:detail AS jsonb),
                         CAST(:short AS jsonb)
                       FROM securities WHERE ticker = :ticker"""
                ),
                {
                    "short": json.dumps(short),
                    "day": today,
                    "agree": result["agree"],
                    "against": result["against"],
                    "blocked": result["blocked"],
                    "detail": json.dumps(result["lenses"]),
                    "ticker": ticker,
                },
            )
        done += 1
    print("reviewed", done)
    return done


if __name__ == "__main__":
    run(get_engine())
    sys.exit(0)
