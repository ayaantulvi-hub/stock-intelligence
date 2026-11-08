"""Portfolio, practice, journal, alerts and reliability. All data here is a TEST FIXTURE."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from stockintel import main, monitor, queries, tools

NOW = datetime(2026, 7, 8, 12, tzinfo=UTC)


def seed(engine, ticker="AAA", cik=1, sic=7370):
    with engine.begin() as conn:
        security = conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank, sic)
                   VALUES (:t, :c, 'Fixture', 'NYSE', :c, :s) RETURNING id"""
            ),
            {"t": ticker, "c": cik, "s": sic},
        ).scalar()
    return security


def bar(engine, security, day, close):
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
                   WHERE name = 'Tiingo' RETURNING id"""
            )
        ).scalar()
        conn.execute(
            text(
                """INSERT INTO price_bars (security_id, fetch_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (:s, :f, :d, now(), :c, :c, :c, :c, 1, 0, 1)"""
            ),
            {"s": security, "f": fetch, "d": day, "c": close},
        )


def own(engine, security, shares=10, paid=200, target=None, stop=None):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO positions (security_id, shares, buy_price, target_price, stop_price)
                   VALUES (:s, :n, :p, :t, :x)"""
            ),
            {"s": security, "n": shares, "p": paid, "t": target, "x": stop},
        )


def test_portfolio_totals_and_warns_about_few_holdings(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 250)
    own(engine, security)
    result = tools.portfolio(engine)
    assert result["worth"] == 2500
    assert result["profit"] == 500
    assert result["holdings"][0]["sector"] == "Services and software"
    assert any("You hold 1 stocks" in risk for risk in result["risks"])


def test_empty_portfolio_works(engine):
    assert tools.portfolio(engine)["holdings"] == []


def test_practice_trades_use_the_latest_close_and_track_cash(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 100)
    assert tools.practice_trade(engine, "AAA", "buy", 10, "Fixture reason") is None
    state = tools.practice_state(engine)
    assert state["cash"] == 9000
    assert state["total"] == 10000
    bar(engine, security, "2026-07-08", 110)
    assert tools.practice_state(engine)["return_percent"] == pytest.approx(1)
    assert tools.practice_trade(engine, "AAA", "sell", 10, "Fixture reason") is None
    assert tools.practice_state(engine)["cash"] == 10100


def test_practice_refuses_what_you_cannot_afford_or_do_not_hold(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 100)
    assert "Not enough" in tools.practice_trade(engine, "AAA", "buy", 1000, "Fixture")
    assert "don't hold" in tools.practice_trade(engine, "AAA", "sell", 1, "Fixture")


def test_practice_with_no_price_is_refused(engine):
    seed(engine)
    assert "No verified price" in tools.practice_trade(engine, "AAA", "buy", 1, "Fixture")


def test_practice_trades_cannot_be_edited(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 100)
    tools.practice_trade(engine, "AAA", "buy", 1, "Fixture")
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("UPDATE practice_trades SET price = 1"))


def test_journal_shows_what_happened_since(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 100)
    assert tools.add_journal(engine, "AAA", "buy", "Fixture reason") is True
    bar(engine, security, "2026-07-08", 90)
    assert tools.journal(engine)[0]["change_percent"] == pytest.approx(-10)


def test_alerts_fire_once_for_target_and_stop(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 150)
    own(engine, security, target=140, stop=None)
    monitor.scan(engine, NOW)
    monitor.scan(engine, NOW)
    messages = monitor.take_unsent(engine)
    assert len(messages) == 1 and "target of 140.00" in messages[0]
    assert monitor.take_unsent(engine) == []


def test_stop_alert(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 90)
    own(engine, security, stop=100)
    monitor.scan(engine, NOW)
    assert "stop of 100.00" in monitor.take_unsent(engine)[0]


def test_unusual_move_alert(engine):
    security = seed(engine)
    tools.watch(engine, "AAA", True)
    start = date(2026, 5, 1)
    for i in range(50):
        bar(engine, security, start + timedelta(days=i), 100 + (i % 2))
    bar(engine, security, "2026-07-07", 140)
    monitor.scan(engine, NOW)
    assert any("usual daily move" in m for m in monitor.take_unsent(engine))


def test_stocks_you_do_not_follow_stay_quiet(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 90)
    monitor.scan(engine, NOW)
    assert monitor.take_unsent(engine) == []


@pytest.mark.parametrize(
    "days, brier, baseline, expected",
    [
        (10, 0.5, 0.67, "Too early to say"),
        (60, 0.5, 0.67, "Better than guessing"),
        (60, 0.67, 0.67, "About the same as guessing"),
        (60, 0.8, 0.67, "Worse than guessing"),
        (60, None, None, "Too early to say"),
        (19, 0.5, 0.67, "Too early to say"),
        (20, 0.5, 0.67, "Early sign: better than guessing"),
    ],
)
def test_grades(days, brier, baseline, expected):
    assert tools.grade(days, brier, baseline) == expected


def test_overconfidence_is_pulled_back():
    pairs = [(0.7, True), (0.7, False), (0.3, True), (0.3, False)] * 10
    assert tools.shrink_factor(pairs, 0.5) == 0


def test_accurate_chances_are_left_alone():
    pairs = [(0.8, True)] * 8 + [(0.8, False)] * 2 + [(0.2, True)] * 2 + [(0.2, False)] * 8
    assert tools.shrink_factor(pairs, 0.5) == pytest.approx(1)


def test_reliability_with_no_scores(engine):
    result = tools.reliability(engine)
    assert result["grade"] == "Too early to say"
    assert result["calibration"] == []


def test_warning_signs():
    report = {
        "metrics": [
            {"name": "Net income", "value": 100.0},
            {"name": "Operating cash flow", "value": 50.0},
            {"name": "Debt to equity", "value": 3.0},
        ],
        "history": [{"net_income": v} for v in (300.0, 200.0, 100.0)],
    }
    found = " ".join(tools.warnings(report))
    assert "well above the cash" in found
    assert "Debt is high" in found
    assert "two years in a row" in found
    assert tools.warnings({"metrics": [], "history": []}) == []


def test_earnings_estimate_uses_last_year_then_a_quarter(engine):
    security = seed(engine)
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
                   WHERE name = 'SEC EDGAR' RETURNING id"""
            )
        ).scalar()
        conn.execute(
            text(
                """INSERT INTO filings (security_id, fetch_id, accession_number, form, filing_date,
                     document_url) VALUES (:s, :f, 'a', '10-Q', '2026-05-01', 'https://fixture.test')"""
            ),
            {"s": security, "f": fetch},
        )
    assert tools.next_earnings(engine, "AAA", date(2026, 6, 1)) == date(2026, 7, 31)
    assert tools.next_earnings(engine, "AAA", date(2027, 4, 1)) == date(2027, 4, 30)
    assert tools.next_earnings(engine, "AAA", date(2027, 9, 1)) is None


def test_market_mood_with_no_data_is_not_verified(engine):
    assert tools.market_mood(engine)["mood"] == "Not verified"


def test_endpoints_refuse_bad_input(engine, monkeypatch):
    seed(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    client = TestClient(main.app)
    body = {"ticker": "AAA", "side": "hold", "shares": 1, "reason": "Fixture"}
    assert client.post("/api/practice", json=body).status_code == 422
    assert client.put("/api/watchlist/ZZZ").status_code == 404
    assert client.put("/api/watchlist/AAA").json() == ["AAA"]
    assert client.delete("/api/watchlist/AAA").json() == []


def test_filing_items_become_plain_words():
    found = tools.read_items("2.02,4.02,9.01")
    assert [item["item"] for item in found] == ["2.02", "4.02"]
    assert found[1]["serious"] is True


def test_only_recent_serious_events_count():
    today = date(2026, 11, 4)
    events = [
        {"date": date(2026, 10, 1), "events": tools.read_items("2.02,2.06")},
        {"date": date(2026, 1, 1), "events": tools.read_items("1.03")},
    ]
    assert tools.serious_events(events, today) == ["Wrote down the value of something it owns"]


def test_a_holding_at_its_stop_says_sell_now_and_alerts_once(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 150)
    own(engine, security, stop=160)
    result = queries.holdings_today(engine, NOW)
    assert result[0]["call"] == "Sell"
    monitor.scan(engine, NOW)
    monitor.scan(engine, NOW)
    messages = monitor.take_unsent(engine)
    assert sum(message.startswith("Sell: AAA") for message in messages) == 1


def test_a_healthy_holding_says_keep(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 150)
    own(engine, security, stop=100)
    assert queries.holdings_today(engine, NOW)[0]["call"] == "Keep"


def test_no_holdings_gives_an_empty_list(engine):
    assert queries.holdings_today(engine, NOW) == []


def test_a_holding_that_flips_to_sell_now_is_reported_and_alerted(engine):
    security = seed(engine)
    bar(engine, security, "2026-07-07", 150)
    own(engine, security, stop=100)
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO holding_calls (ticker, day, call, reason)
                   VALUES ('AAA', '2026-07-07', 'Keep', 'Fixture')"""
            )
        )
        conn.execute(text("UPDATE positions SET stop_price = 160"))
    monitor.scan(engine, NOW)
    messages = monitor.take_unsent(engine)
    assert any("AAA changed. Your holding: Keep to Sell" in message for message in messages)
