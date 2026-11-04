"""Today's orders. TEST FIXTURE values only."""

from datetime import date

from stockintel import queries


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
