"""Daily keep or sell rules. TEST FIXTURE values only."""

from datetime import date

from stockintel import advice

TODAY = date(2026, 11, 18)
PLAIN = {
    "price": 100.0,
    "stop": 90.0,
    "sell_by": date(2026, 12, 3),
    "today": TODAY,
    "stale": False,
    "rank": 0.8,
    "blocked": None,
    "bearish_candle": None,
    "below_50": False,
}


def call(**changes):
    return advice.keep_or_sell(**{**PLAIN, **changes})


def test_keep_when_nothing_is_wrong_and_shows_the_date():
    result = call()
    assert result["call"] == "Keep"
    assert "2026-12-03" in result["reason"]


def test_sell_now_when_the_stop_is_hit():
    assert call(price=89.0)["call"] == "Sell now"


def test_sell_now_on_the_planned_date():
    assert call(today=date(2026, 12, 3))["call"] == "Sell now"


def test_sell_now_when_the_ranking_drops():
    result = call(rank=0.2)
    assert result["call"] == "Sell now"
    assert "bottom 30%" in result["reason"]


def test_sell_now_on_serious_trouble():
    assert call(blocked="a filing")["call"] == "Sell now"


def test_bearish_candle_needs_the_trend_to_agree():
    assert call(bearish_candle="Shooting star")["call"] == "Keep"
    assert call(bearish_candle="Shooting star", below_50=True)["call"] == "Sell now"


def test_old_prices_give_no_call():
    assert call(stale=True, rank=0.1)["call"] == "Wait"
