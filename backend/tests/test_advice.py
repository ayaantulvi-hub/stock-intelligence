"""Factor leans and positions. All inputs here are TEST FIXTURES."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from stockintel import advice, main, queries
from stockintel.advice import factor_leans, lean_for, position_view


@pytest.mark.parametrize(
    "percentile, direction, expected",
    [
        (90, 1, "Buy"),
        (10, 1, "Sell"),
        (90, -1, "Sell"),
        (10, -1, "Buy"),
        (50, 1, "No lean"),
        (90, None, "No lean"),
        (None, 1, "No lean"),
    ],
)
def test_lean_direction(percentile, direction, expected):
    assert lean_for(percentile, direction) == expected


def test_tested_result_outranks_the_paper():
    # The paper says low momentum is bad, but this fixture test says it did better.
    tests = {"mom_12_1": {"t_stat": -4.0, "spread": -0.02}}
    row = factor_leans([{"factor": "mom_12_1", "percentile": 10}], tests)["factors"][0]
    assert row["lean"] == "Buy"
    assert row["proven"] is True


def test_failed_test_falls_back_to_the_paper_and_says_so():
    tests = {"mom_12_1": {"t_stat": 1.0, "spread": 0.01}}
    result = factor_leans([{"factor": "mom_12_1", "percentile": 90}], tests)
    assert result["factors"][0]["evidence"].startswith("Paper only: failed")
    assert result["proven_buy"] == 0
    assert result["paper_buy"] == 1


def test_proven_and_unproven_are_counted_apart():
    tests = {"value": {"t_stat": 3.5, "spread": 0.02}}
    drivers = [
        {"factor": "value", "percentile": 95},
        {"factor": "size", "percentile": 95},
        {"factor": "rsi", "percentile": 95},
    ]
    result = factor_leans(drivers, tests)
    assert (result["proven_buy"], result["paper_sell"]) == (1, 1)
    assert result["factors"][-1]["lean"] == "No lean"


def position(**changes):
    return {
        "shares": 10.0,
        "buy_price": 200.0,
        "target_price": None,
        "stop_price": None,
        **changes,
    }


def test_profit_and_break_even():
    result = position_view(position(), 250.0, "No reliable edge", [])
    assert result["profit"] == 500
    assert result["profit_percent"] == 25
    assert result["break_even"] == pytest.approx(200.2)


def test_plan_reports_target_and_stop():
    hit = position_view(position(target_price=240.0), 250.0, "No reliable edge", [])
    assert "target of 240.00 has been reached" in hit["plan"]
    stopped = position_view(position(stop_price=260.0), 250.0, "No reliable edge", [])
    assert "stop of 260.00" in stopped["plan"]
    assert "not set" in position_view(position(), 250.0, "No reliable edge", [])["plan"]


def test_price_paid_never_changes_the_call():
    low = position_view(position(buy_price=100.0), 250.0, "Sell candidate", [])
    high = position_view(position(buy_price=900.0), 250.0, "Sell candidate", [])
    assert low["call"] == high["call"]


def test_no_edge_gives_no_sell_call():
    assert position_view(position(), 250.0, "No reliable edge", [])["call"].startswith(
        "No sell call"
    )


def test_cases_compare_with_price_paid():
    cases = [{"name": "Base", "value": 300.0, "against_price": 0.2}]
    assert (
        position_view(position(), 250.0, "No reliable edge", cases)["cases"][0]["from_cost"] == 0.5
    )


def seed(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('AAA', 1, 'Fixture', 'NYSE', 1)"""
            )
        )


def test_position_saves_updates_and_deletes(engine, monkeypatch):
    seed(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    client = TestClient(main.app)
    body = {"shares": 10, "buy_price": 200}
    assert client.put("/api/stocks/AAA/position", json=body).status_code == 200
    assert client.put("/api/stocks/AAA/position", json={**body, "shares": 5}).status_code == 200
    assert queries.get_position(engine, "AAA")["shares"] == 5
    assert queries.get_position(engine, "AAA")["price"] is None
    client.delete("/api/stocks/AAA/position")
    assert queries.get_position(engine, "AAA") is None


def test_position_rejects_bad_numbers_and_unknown_stocks(engine, monkeypatch):
    seed(engine)
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    client = TestClient(main.app)
    assert (
        client.put("/api/stocks/AAA/position", json={"shares": 0, "buy_price": 1}).status_code
        == 422
    )
    assert (
        client.put("/api/stocks/ZZZ/position", json={"shares": 1, "buy_price": 1}).status_code
        == 404
    )


def test_no_forecast_means_no_leans(engine):
    seed(engine)
    assert queries.stock_leans(engine, "AAA") is None


def test_every_directional_factor_is_real():
    from stockintel.factors import NAMES

    assert set(advice.PAPER_DIRECTION) <= set(NAMES)


def review(**changes):
    values = {
        "stale": False,
        "action": "No reliable edge",
        "above_200": True,
        "report": {},
        "insider_net": None,
        "last_earnings_days": None,
        "position": None,
        "portfolio_share": None,
        **changes,
    }
    return {check["topic"]: check for check in advice.checklist(**values)}


def test_no_edge_and_missing_data_are_not_passes():
    checks = review()
    assert checks["Tested edge"]["state"] == "caution"
    assert checks["Margin of safety"]["state"] == "unknown"
    assert checks["Debt"]["state"] == "unknown"
    assert checks["Your exit plan"]["state"] == "caution"


def test_margin_of_safety_needs_a_15_percent_cushion():
    report = {"cases": [{"name": "Base", "against_price": 0.1}]}
    assert review(report=report)["Margin of safety"]["state"] == "caution"
    report = {"cases": [{"name": "Base", "against_price": 0.2}]}
    assert review(report=report)["Margin of safety"]["state"] == "pass"


def test_negative_equity_is_not_a_low_debt_pass():
    report = {"metrics": [{"name": "Debt to equity", "value": -3.0}]}
    assert review(report=report)["Debt"]["state"] == "caution"


def test_concentration_flags_more_than_10_percent():
    assert review(portfolio_share=0.4)["Concentration"]["state"] == "caution"
    assert review(portfolio_share=0.05)["Concentration"]["state"] == "pass"
    assert "Concentration" not in review()


def test_insider_selling_and_late_earnings_are_cautions():
    assert review(insider_net=-5.0)["Insiders"]["state"] == "caution"
    assert review(last_earnings_days=80)["Earnings"]["state"] == "caution"
    assert review(last_earnings_days=10)["Earnings"]["state"] == "pass"


def test_checklist_works_for_a_stock_with_no_data(engine):
    seed(engine)
    checks = {check["topic"]: check for check in queries.stock_checklist(engine, "AAA")}
    assert checks["Data"]["state"] == "caution"
    assert queries.stock_checklist(engine, "ZZZ") is None


def test_survivorship_suspect_pass_is_not_proven():
    tests = {"size": {"t_stat": -5.9, "spread": -0.012}}
    row = factor_leans([{"factor": "size", "percentile": 10}], tests)["factors"][0]
    assert row["proven"] is False
    assert row["lean"] == "No lean"
    assert "distrusted" in row["evidence"]


@pytest.mark.parametrize(
    "action, rank, lean, proven",
    [
        ("No reliable edge", 0.85, "Buy", False),
        ("No reliable edge", 0.15, "Sell", False),
        ("No reliable edge", 0.5, "Mixed", False),
        ("Buy candidate", 0.95, "Buy", True),
        ("Sell candidate", 0.05, "Sell", True),
        ("No reliable edge", None, "No lean", False),
    ],
)
def test_overall_lean_is_marked_unless_tested(action, rank, lean, proven):
    result = advice.overall(action, rank)
    assert (result["lean"], result["proven"], result["decision"]) == (lean, proven, action)


def test_every_check_says_what_it_means():
    for check in review(insider_net=1.0, last_earnings_days=80, portfolio_share=0.5).values():
        assert check["meaning"]


def test_factor_reading_is_explained_in_plain_words():
    row = factor_leans([{"factor": "size", "percentile": 95}], {})["factors"][0]
    assert "larger company" in row["meaning"]
    assert "unproven here" in row["meaning"]
    middle = factor_leans([{"factor": "size", "percentile": 50}], {})["factors"][0]
    assert "middle" in middle["meaning"]


OWNED = {"profit": 100.0, "price": 150.0, "stop_price": None, "target_price": None}
EDGELESS = "No reliable edge"


@pytest.mark.parametrize(
    "action, rank, stale, position, call, proven",
    [
        (EDGELESS, 0.9, True, None, "Wait", False),
        ("Buy candidate", 0.95, False, None, "Buy", True),
        ("Buy candidate", 0.95, False, OWNED, "Hold", True),
        ("Sell candidate", 0.05, False, None, "Don't buy", True),
        ("Sell candidate", 0.05, False, OWNED, "Sell", True),
        ("No action", 0.5, False, OWNED, "Hold", True),
        (EDGELESS, 0.9, False, None, "Leans buy", False),
        (EDGELESS, 0.1, False, None, "Leans don't buy", False),
        (EDGELESS, 0.1, False, OWNED, "Hold and review", False),
        (EDGELESS, 0.5, False, None, "Wait", False),
        (None, None, False, OWNED, "Hold", False),
    ],
)
def test_decision(action, rank, stale, position, call, proven):
    result = advice.decision(action, rank, stale, position)
    assert (result["call"], result["proven"]) == (call, proven)


def test_owners_stop_and_target_come_first():
    stopped = {**OWNED, "stop_price": 160.0}
    assert advice.decision(EDGELESS, 0.9, False, stopped)["call"] == "Sell"
    hit = {**OWNED, "target_price": 140.0}
    assert advice.decision(EDGELESS, 0.9, False, hit)["call"] == "Sell or take some profit"


def test_price_paid_does_not_change_the_decision():
    cheap = {**OWNED, "buy_price": 10.0}
    dear = {**OWNED, "buy_price": 900.0}
    assert advice.decision(EDGELESS, 0.2, False, cheap) == advice.decision(
        EDGELESS, 0.2, False, dear
    )


ANSWER = {"call": "Leans buy", "reason": "Fixture.", "proven": False, "kind": "buy", "owned": False}
LINES = [
    {"tone": "good", "text": "Up trend."},
    {"tone": "bad", "text": "Weak recent trend."},
    {"tone": "neutral", "text": "Ignored."},
]
CHECKS = [
    {"topic": "Debt", "state": "pass", "text": "Low debt."},
    {"topic": "Insiders", "state": "caution", "text": "Insider selling."},
    {"topic": "Tested edge", "state": "caution", "text": "Left out."},
]
LEVELS = {"stop": 90.0, "target": 120.0}


def test_brief_gives_reasons_each_way_and_a_next_step():
    result = advice.brief(ANSWER, LINES, CHECKS, LEVELS, None)
    assert result["reasons_for"] == ["Up trend.", "Low debt."]
    assert result["reasons_against"] == ["Weak recent trend.", "Insider selling."]
    assert "90.00" in result["next_step"] and "120.00" in result["next_step"]


def test_reasons_are_limited_to_three():
    many = [{"tone": "good", "text": str(i)} for i in range(9)]
    assert len(advice.brief(ANSWER, many, [], None, None)["reasons_for"]) == 3


def test_owners_own_prices_are_used():
    position = {"stop_price": 80.0, "target_price": 150.0}
    step = advice.next_step("Hold", LEVELS, position)
    assert "80.00" in step and "150.00" in step


@pytest.mark.parametrize(
    "call",
    [
        "Wait",
        "Buy",
        "Leans buy",
        "Don't buy",
        "Leans don't buy",
        "Sell",
        "Hold",
        "Hold and review",
        "Sell or take some profit",
    ],
)
def test_every_call_has_a_next_step(call):
    assert advice.next_step(call, None, None)
