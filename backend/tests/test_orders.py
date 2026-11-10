"""Today's orders. TEST FIXTURE values only."""

from datetime import date

import pytest
from sqlalchemy import text

from stockintel import queries, set_holdings


def test_orders_with_no_forecasts_are_empty(engine):
    result = queries.orders(engine)
    assert result["orders"] == []
    assert result["sell_by"] is None


def test_sell_by_is_twenty_trading_days_later(engine, monkeypatch):
    card = {"ticker": "AAA", "name": "A", "rank": 1, "price": 100.0, "reasons": []}
    monkeypatch.setattr(
        queries,
        "ideas",
        lambda e, n: {"target_session": date(2026, 11, 4), "edge": False, "top": [card]},
    )
    monkeypatch.setattr(queries, "suggested_levels", lambda e, t: {"levels": {"stop": 90.0}})
    result = queries.orders(engine)
    assert result["sell_by"] == date(2026, 12, 3)
    assert result["orders"][0]["stop"] == 90.0


def _security(conn, ticker, rank):
    return conn.execute(
        text(
            """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
               VALUES (:t, :c, :t, 'NYSE', :r) RETURNING id"""
        ),
        {"t": ticker, "c": str(rank), "r": rank},
    ).scalar()


def test_set_holdings_replaces_the_list_and_refuses_unknown_tickers(engine):
    with engine.begin() as conn:
        _security(conn, "HOLDA", 9001)
        _security(conn, "HOLDB", 9002)
    item = {"ticker": "HOLDA", "shares": 16, "buy_price": 597.15, "sell_by": "2026-12-03"}
    other = {"ticker": "HOLDB", "shares": 10, "buy_price": 20.0, "stop_price": 15.0}
    set_holdings.apply(engine, [item, other])
    set_holdings.apply(engine, [item])
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """SELECT s.ticker, p.shares, p.buy_price, p.stop_price, p.sell_by FROM positions p
                   JOIN securities s ON s.id = p.security_id"""
            )
        ).all()
    assert [(r.ticker, r.shares, r.buy_price, r.stop_price, str(r.sell_by)) for r in rows] == [
        ("HOLDA", 16, 597.15, None, "2026-12-03")
    ]
    with pytest.raises(ValueError, match="NOPE"):
        set_holdings.apply(engine, [{"ticker": "NOPE", "shares": 1, "buy_price": 1.0}])
    assert get_count(engine) == 1


def get_count(engine):
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM positions")).scalar()


def test_a_reported_sale_price_replaces_the_estimate(engine):
    with engine.begin() as conn:
        _security(conn, "HOLDC", 9003)
    set_holdings.apply(engine, [{"ticker": "HOLDC", "shares": 20, "buy_price": 378.46}])
    set_holdings.apply(engine, [])
    set_holdings.record_sales(engine, [{"ticker": "HOLDC", "price": 318.0}])
    with engine.connect() as conn:
        assert conn.execute(text("SELECT exit_price FROM closed_trades")).scalar() == 318.0
    with pytest.raises(ValueError, match="NOPE"):
        set_holdings.record_sales(engine, [{"ticker": "NOPE", "price": 1.0}])
