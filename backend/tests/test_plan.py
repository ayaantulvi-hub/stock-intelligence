"""Trading plan rules. Every price here is a TEST FIXTURE."""

from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import text

from stockintel import plan, queries, set_holdings, stops

NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


def add_stock(conn, ticker, rank, closes):
    sid = conn.execute(
        text(
            """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
               VALUES (:t, :c, :t, 'NYSE', :r) RETURNING id"""
        ),
        {"t": ticker, "c": str(rank), "r": rank},
    ).scalar()
    fetch = conn.execute(
        text(
            """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
               SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
               LIMIT 1 RETURNING id"""
        )
    ).scalar()
    start = date(2026, 1, 1)
    for i, close in enumerate(closes):
        conn.execute(
            text(
                """INSERT INTO price_bars (fetch_id, security_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (:f, :s, :d, :d, :c, :c * 1.01, :c * 0.99, :c, 1000, 0, 1)"""
            ),
            {"f": fetch, "s": sid, "d": start + timedelta(days=i), "c": close},
        )
    return sid


def walk(seed, n=120):
    rng = np.random.default_rng(seed)
    return list(100 * np.cumprod(1 + rng.normal(0, 0.01, n)))


def test_moving_together_finds_the_matching_pair():
    base = pd.Series(walk(1))
    other = pd.Series(walk(2))
    frames = {
        name: pd.DataFrame({"market_date": range(120), "close": closes})
        for name, closes in {"AAA": base, "BBB": base * 1.5, "CCC": other}.items()
    }
    assert plan.groups(frames) == [["AAA", "BBB"]]


def test_plan_flags_missing_stops_correlation_and_risk(engine):
    closes = walk(3)
    with engine.begin() as conn:
        add_stock(conn, "AAA", 1, closes)
        add_stock(conn, "BBB", 2, [c * 2 for c in closes])
    queries.save_position(
        engine, "AAA", {"shares": 10, "buy_price": 100, "target_price": None, "stop_price": None}
    )
    queries.save_position(
        engine, "BBB", {"shares": 10, "buy_price": 200, "target_price": None, "stop_price": 1.0}
    )
    result = plan.review(engine, now=NOW)
    rules = {check["rule"]: check for check in result["checks"]}
    assert rules["A stop on every holding"]["state"] == "fail"
    assert "AAA" in rules["A stop on every holding"]["text"]
    assert rules["Stocks that move together"]["state"] == "fail"
    assert rules["Risk per holding"]["state"] == "fail"


def test_a_widened_stop_is_caught_and_a_raised_one_is_not(engine):
    with engine.begin() as conn:
        add_stock(conn, "AAA", 1, walk(4))
    values = {"shares": 1, "buy_price": 100, "target_price": None, "stop_price": 90.0}
    queries.save_position(engine, "AAA", values)
    queries.save_position(engine, "AAA", {**values, "stop_price": 95.0})
    assert plan.week(engine, datetime.now(UTC))["widened"] == []
    queries.save_position(engine, "AAA", {**values, "stop_price": 80.0})
    assert plan.week(engine, datetime.now(UTC))["widened"] == ["AAA"]


def test_three_losing_sales_pause_new_buys(engine):
    with engine.begin() as conn:
        for rank, ticker in enumerate(["AAA", "BBB", "CCC"], 1):
            add_stock(conn, ticker, rank, [50.0] * 30)
    items = [{"ticker": t, "shares": 1, "buy_price": 60.0} for t in ("AAA", "BBB", "CCC")]
    set_holdings.apply(engine, items)
    assert plan.losing_streak(engine) == 0
    set_holdings.apply(engine, items[:1])
    queries.delete_position(engine, "AAA")
    assert plan.losing_streak(engine) == 3
    assert queries.orders(engine)["paused"] is True
    week = plan.week(engine, datetime.now(UTC))
    assert week["sales"] == 3 and week["losses"] == 3 and week["net"] == -30.0


def test_a_trailing_stop_only_rises_and_uses_known_prices():
    closes = [100.0] * 20 + [110.0, 120.0, 90.0] + [90.0] * 30
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": [c + 1 for c in closes],
            "low": [c - 1 for c in closes],
            "close": closes,
        }
    )
    fixed = stops.simulate(frame, 3.0)
    trailed = stops.simulate(frame, 3.0, trailing=True)
    assert len(fixed) == len(trailed)
    assert trailed[0][0] >= fixed[0][0]
    assert stops.study({(3.0, True): trailed})[0]["trailing"] is True


def test_not_chasing_price():
    assert plan.not_chasing(100.0, 4.0) == 102.0
    assert plan.not_chasing(100.0, None) is None
