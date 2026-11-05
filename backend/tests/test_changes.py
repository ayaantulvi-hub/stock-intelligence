"""What changed. TEST FIXTURE values only."""

from datetime import date

from stockintel import changes

NOW = date(2026, 11, 5)
LOW, MID, HIGH = (0.1, "No reliable edge"), (0.5, "No reliable edge"), (0.9, "No reliable edge")


def test_a_lean_flip_is_reported_with_its_direction():
    found = changes.lean_changes({"AAA": MID, "BBB": HIGH}, {"AAA": HIGH, "BBB": LOW})
    leans = {row["ticker"]: row for row in found if row["topic"] == "Decision"}
    assert (leans["AAA"]["was"], leans["AAA"]["now"]) == ("Wait", "Leans buy")
    assert leans["AAA"]["tone"] == changes.BETTER
    assert (leans["BBB"]["was"], leans["BBB"]["now"]) == ("Leans buy", "Leans don't buy")
    assert leans["BBB"]["tone"] == changes.WORSE


def test_an_expert_warning_shows_as_a_decision_change():
    found = changes.lean_changes({"AAA": HIGH}, {"AAA": HIGH}, {}, {"AAA": "a filing"})
    decision = next(row for row in found if row["topic"] == "Decision")
    assert (decision["was"], decision["now"]) == ("Leans buy", "Hold off")


def test_a_new_stock_is_not_called_a_change():
    assert changes.lean_changes({"AAA": MID}, {"AAA": MID, "ZZZ": HIGH}) == []


def test_top_ten_moves():
    old = {f"S{i}": (1 - i / 100, "No reliable edge") for i in range(12)}
    new = dict(old)
    new["S11"] = (2.0, "No reliable edge")
    found = [row for row in changes.lean_changes(old, new) if row["topic"] == "Top 10"]
    assert {(row["ticker"], row["tone"]) for row in found} == {
        ("S11", changes.BETTER),
        ("S9", changes.WORSE),
    }


def review(blocked=None, verdict="good", short=None):
    names = [{"name": name, "verdict": verdict} for name in changes.horizons.LONG_LENSES]
    return {"blocked": blocked, "detail": names, "short": short}


def test_warnings_and_long_term_changes():
    found = changes.review_changes({"AAA": review()}, {"AAA": review("a filing")})
    topics = {row["topic"]: row for row in found}
    assert topics["Warning"]["now"] == "Hold off"
    assert topics["Long-term"]["now"] == "Avoid for now"


def test_short_trade_change():
    was = review(short={"call": "No trade", "kind": "neutral", "reason": "x"})
    now = review(short={"call": "Leans buy, short trade", "kind": "buy", "reason": "Hammer"})
    found = changes.review_changes({"AAA": was}, {"AAA": now})
    assert found[0]["topic"] == "Short trade" and found[0]["tone"] == changes.BETTER


def test_no_history_means_no_changes(engine):
    result = changes.build(engine, NOW)
    assert result["decisions"] == [] and result["details"] == []


def test_each_change_says_what_to_do():
    assert changes.what_to_do({"call": "Keep"}, True).startswith("Keep. Don't sell")
    assert changes.what_to_do({"call": "Sell now", "reason": "Stop."}, True) == "Sell now. Stop."
    assert changes.what_to_do(None, True) == "You don't own it, so nothing to do."
    assert changes.what_to_do(None, False) == "No action."
