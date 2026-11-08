"""Trading plan rules, checked by the tool rather than ticked by hand.

The rules come from a standard trading plan: a stop on every holding, a stop is never widened,
limited risk per holding, not too much money in stocks that move together, a pause after a
losing streak, and a weekly review. The thresholds are plan rules, not tested forecasts.
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel import charts, stops

MAX_RISK_SHARE = 0.015  # The owner's one limit for every page: lose at most 1.5% a trade.
TOGETHER = 0.7  # Daily moves this correlated over 60 days count as moving together.
TOGETHER_DAYS = 60
LOSING_STREAK = 3  # Pause new buys after this many losing sales in a row.
NOT_CHASING_ATR = 0.5  # Skip a buy if the live price is this many typical days' moves higher.
BARS = 260


def _check(rule: str, state: str, text_: str) -> dict:
    return {"rule": rule, "state": state, "text": text_}


def _frames(engine: Engine) -> tuple[list, dict]:
    query = """SELECT s.id, s.ticker, p.shares, p.buy_price, p.stop_price, p.sell_by
               FROM positions p JOIN securities s ON s.id = p.security_id ORDER BY s.ticker"""
    bars = """SELECT * FROM (SELECT DISTINCT ON (market_date) market_date, open, high, low,
                close, volume, div_cash, split_factor FROM price_bars WHERE security_id = :id
                ORDER BY market_date DESC, id DESC LIMIT :n) AS recent ORDER BY market_date"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
        frames = {}
        for row in rows:
            found = conn.execute(text(bars), {"id": row.id, "n": BARS}).all()
            if found:
                frames[row.ticker] = charts.adjust(pd.DataFrame([b._mapping for b in found]))
    return rows, frames


def groups(frames: dict[str, pd.DataFrame]) -> list[list[str]]:
    """Holdings whose daily moves were strongly correlated, joined into groups."""
    returns = pd.DataFrame(
        {
            ticker: frame.set_index("market_date")["close"].pct_change()
            for ticker, frame in frames.items()
        }
    ).tail(TOGETHER_DAYS)
    tickers = [t for t in returns.columns if returns[t].count() >= TOGETHER_DAYS // 2]
    if len(tickers) < 2:
        return []
    matrix = returns[tickers].corr()
    parent = {t: t for t in tickers}

    def root(t):
        while parent[t] != t:
            t = parent[t]
        return t

    for i, a in enumerate(tickers):
        for b in tickers[i + 1 :]:
            if matrix.loc[a, b] >= TOGETHER:
                parent[root(b)] = root(a)
    found: dict[str, list[str]] = {}
    for t in tickers:
        found.setdefault(root(t), []).append(t)
    return sorted((sorted(g) for g in found.values() if len(g) > 1), key=len, reverse=True)


def trailing_tested(engine: Engine) -> dict | None:
    """The latest stop test, if a trailing stop beat the same fixed stop on average return."""
    query = """SELECT stop_multiple, trails, avg_return, worst_return FROM stop_studies
               WHERE run_at = (SELECT max(run_at) FROM stop_studies)
                 AND stop_multiple = :m"""
    with engine.connect() as conn:
        rows = {r.trails: r for r in conn.execute(text(query), {"m": stops.DEFAULT_MULTIPLE})}
    if True not in rows or False not in rows:
        return None
    return {
        "better": rows[True].avg_return > rows[False].avg_return,
        "trailing": rows[True].avg_return,
        "fixed": rows[False].avg_return,
    }


def losing_streak(engine: Engine) -> int:
    query = """SELECT exit_price < buy_price AS lost FROM closed_trades
               WHERE exit_price IS NOT NULL ORDER BY closed_at DESC, id DESC LIMIT :n"""
    with engine.connect() as conn:
        lost = list(conn.execute(text(query), {"n": LOSING_STREAK}).scalars())
    streak = 0
    for item in lost:
        if not item:
            break
        streak += 1
    return streak


def review(engine: Engine, account: float | None = None, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    rows, frames = _frames(engine)
    holdings, checks = [], []
    tested = trailing_tested(engine)
    for row in rows:
        frame = frames.get(row.ticker)
        price = float(frame["close"].iloc[-1]) if frame is not None else None
        suggested = stops.suggest(frame) if frame is not None else None
        raised = None
        if tested and tested["better"] and row.stop_price and suggested and frame is not None:
            high = float(frame["close"].tail(stops.HOLD_DAYS).max())
            level = high - stops.DEFAULT_MULTIPLE * suggested["atr"]
            raised = level if level > row.stop_price else None
        holdings.append(
            {
                "ticker": row.ticker,
                "price": price,
                "worth": None if price is None else price * row.shares,
                "stop": row.stop_price,
                "suggested_stop": suggested["stop"] if suggested else None,
                "raise_stop_to": raised,
                "risk": None
                if price is None or not row.stop_price
                else max(price - row.stop_price, 0) * row.shares,
                "sell_by": row.sell_by,
            }
        )
    if not holdings:
        return {
            "checks": [],
            "holdings": [],
            "groups": [],
            "paused": False,
            "week": week(engine, now),
        }
    worth = sum(h["worth"] or 0 for h in holdings)
    base = account or worth
    base_name = "your account" if account else "the money in your stocks"

    missing = [h for h in holdings if not h["stop"]]
    if missing:
        names = ", ".join(
            h["ticker"] + (f" (suggested {h['suggested_stop']:.2f})" if h["suggested_stop"] else "")
            for h in missing
        )
        checks.append(_check("A stop on every holding", "fail", f"No stop on {names}."))
    else:
        checks.append(_check("A stop on every holding", "pass", "Every holding has a stop."))

    big = [
        h for h in holdings if h["risk"] is not None and base and h["risk"] / base > MAX_RISK_SHARE
    ]
    if big:
        detail = ", ".join(f"{h['ticker']} {h['risk'] / base:.1%}" for h in big)
        checks.append(
            _check(
                "Risk per holding",
                "fail",
                f"If these hit their stop you'd lose more than {MAX_RISK_SHARE:.1%} of "
                f"{base_name}: {detail}.",
            )
        )
    elif not missing:
        checks.append(
            _check(
                "Risk per holding",
                "pass",
                f"No holding risks more than {MAX_RISK_SHARE:.1%} of {base_name}.",
            )
        )

    together = groups(frames)
    for group in together:
        share = (
            sum(h["worth"] or 0 for h in holdings if h["ticker"] in group) / worth if worth else 0
        )
        state = "fail" if share > 0.5 else "caution"
        checks.append(
            _check(
                "Stocks that move together",
                state,
                f"{', '.join(group)} have moved together over the last {TOGETHER_DAYS} days, "
                f"so they tend to rise and fall at once. They are {share:.0%} of your money.",
            )
        )
    if not together and len(frames) > 1:
        checks.append(
            _check("Stocks that move together", "pass", "No two holdings move closely together.")
        )

    widened = week(engine, now)["widened"]
    if widened:
        checks.append(
            _check(
                "Never widen a stop",
                "fail",
                "You moved a stop further away this week on " + ", ".join(widened) + ".",
            )
        )

    streak = losing_streak(engine)
    paused = streak >= LOSING_STREAK
    if paused:
        checks.append(
            _check(
                "Pause after losses",
                "fail",
                f"Your last {streak} sales were losses. The plan says stop buying until you've "
                "reviewed them.",
            )
        )
    raises = [h for h in holdings if h["raise_stop_to"]]
    if raises:
        checks.append(
            _check(
                "Trailing stop",
                "caution",
                "Tested better than a fixed stop. Raise "
                + ", ".join(f"{h['ticker']} to {h['raise_stop_to']:.2f}" for h in raises)
                + ".",
            )
        )
    return {
        "checks": checks,
        "holdings": holdings,
        "groups": together,
        "paused": paused,
        "trailing": tested,
        "base": base_name,
        "week": week(engine, now),
    }


def week(engine: Engine, now: datetime) -> dict:
    """The last 7 days: sales, rules broken, and how the model did."""
    since = now - timedelta(days=7)
    with engine.connect() as conn:
        sales = conn.execute(
            text(
                """SELECT s.ticker, c.shares, c.buy_price, c.exit_price FROM closed_trades c
                   JOIN securities s ON s.id = c.security_id
                   WHERE c.closed_at >= :since AND c.exit_price IS NOT NULL"""
            ),
            {"since": since},
        ).all()
        changes = conn.execute(
            text(
                """SELECT s.ticker, c.old_stop, c.new_stop FROM stop_changes c
                   JOIN securities s ON s.id = c.security_id WHERE c.changed_at >= :since"""
            ),
            {"since": since},
        ).all()
        late = list(
            conn.execute(
                text(
                    """SELECT s.ticker FROM positions p JOIN securities s ON s.id = p.security_id
                       WHERE p.sell_by < :today ORDER BY s.ticker"""
                ),
                {"today": now.date()},
            ).scalars()
        )
        scored = conn.execute(
            text(
                """SELECT f.p_up, f.p_flat, f.p_down, sc.outcome, sc.in_range
                   FROM forecast_scores sc JOIN forecasts f ON f.id = sc.forecast_id
                   WHERE sc.scored_at >= :since"""
            ),
            {"since": since},
        ).all()
    results = [(r.exit_price - r.buy_price) * r.shares for r in sales]
    wins = sum(1 for r in results if r > 0)
    calls = [
        max(("up", r.p_up), ("flat", r.p_flat), ("down", r.p_down), key=lambda x: x[1])[0]
        == r.outcome
        for r in scored
    ]
    outcomes = [r.outcome for r in scored]
    # What guessing gives: always calling the outcome that was most common that week.
    usual = max((outcomes.count(o) for o in set(outcomes)), default=0)
    best = max(zip(results, sales), default=None, key=lambda x: x[0])
    worst = min(zip(results, sales), default=None, key=lambda x: x[0])
    return {
        "sales": len(results),
        "wins": wins,
        "losses": len(results) - wins,
        "win_rate": wins / len(results) if results else None,
        "net": float(np.sum(results)) if results else None,
        "best": None if best is None else {"ticker": best[1].ticker, "result": best[0]},
        "worst": None if worst is None else {"ticker": worst[1].ticker, "result": worst[0]},
        "widened": sorted(
            {
                c.ticker
                for c in changes
                if c.old_stop is not None and (c.new_stop is None or c.new_stop < c.old_stop)
            }
        ),
        "past_sell_date": late,
        "model_calls": len(calls),
        "model_right": sum(calls),
        "model_usual": usual,
        "model_in_range": sum(1 for r in scored if r.in_range),
    }


def not_chasing(price: float, atr: float | None) -> float | None:
    """The highest price worth paying today: the last close plus half a typical day's move."""
    return None if atr is None else price + NOT_CHASING_ATR * atr


if __name__ == "__main__":
    from stockintel.db import get_engine

    result = review(get_engine())
    for check in result["checks"]:
        print(check["state"], "|", check["rule"], "|", check["text"])
    print("week", result["week"])
