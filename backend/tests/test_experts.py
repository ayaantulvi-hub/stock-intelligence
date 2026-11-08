"""Expert review rules. Every company here is a TEST FIXTURE."""

from datetime import date

import numpy as np
import pandas as pd

from stockintel import advice, experts, longterm


def row(tag, value, year, start=True, form="10-K"):
    return {
        "tag": tag,
        "unit": "USD",
        "period_start": date(year, 1, 1) if start else None,
        "period_end": date(year, 12, 31),
        "value": value,
        "accession_number": f"a{year}",
        "fiscal_period": "FY",
        "form": form,
        "filed": date(year + 1, 2, 1),
        "document_url": "https://www.sec.gov/test-fixture",
    }


def healthy() -> pd.DataFrame:
    rows = []
    for year, income, cash, assets, debt, current, owed_soon, gross, sales in (
        (2024, 10.0, 12.0, 100.0, 30.0, 40.0, 20.0, 40.0, 100.0),
        (2025, 15.0, 20.0, 110.0, 25.0, 50.0, 20.0, 50.0, 120.0),
    ):
        rows += [
            row("NetIncomeLoss", income, year),
            row("NetCashProvidedByUsedInOperatingActivities", cash, year),
            row("Assets", assets, year, False),
            row("LongTermDebt", debt, year, False),
            row("AssetsCurrent", current, year, False),
            row("LiabilitiesCurrent", owed_soon, year, False),
            row("GrossProfit", gross, year),
            row("Revenues", sales, year),
            row("EntityCommonStockSharesOutstanding", 10.0, year, False),
        ]
    return pd.DataFrame(rows)


def test_a_clearly_improving_company_passes_every_health_test():
    table = longterm.fscore_table(healthy())
    assert table["fscore"].iloc[-1] == 9
    assert table["tests"].iloc[-1] == 9


def test_too_few_figures_give_no_health_score():
    facts = healthy()
    facts = facts[facts["tag"].isin(["Assets", "NetIncomeLoss"])]
    assert np.isnan(longterm.fscore_table(facts)["fscore"].iloc[-1])
    assert experts.piotroski(facts)["verdict"] == experts.UNKNOWN


def test_altman_matches_a_worked_sum():
    facts = pd.concat(
        [
            healthy(),
            pd.DataFrame(
                [
                    row("RetainedEarningsAccumulatedDeficit", 20.0, 2025, False),
                    row("OperatingIncomeLoss", 22.0, 2025),
                    row("Liabilities", 55.0, 2025, False),
                ]
            ),
        ]
    )
    expected = 1.2 * 30 / 110 + 1.4 * 20 / 110 + 3.3 * 22 / 110 + 0.6 * 200 / 55 + 120 / 110
    assert abs(longterm.altman_z(facts, 200.0) - expected) < 1e-9


def test_altman_needs_every_part():
    assert longterm.altman_z(healthy(), 200.0) is None
    assert longterm.altman_z(healthy(), None) is None


def test_banks_and_utilities_get_no_altman_score():
    assert experts.altman(healthy(), 200.0, 6021)["verdict"] == experts.UNKNOWN
    assert experts.altman(healthy(), 200.0, 4911)["verdict"] == experts.UNKNOWN


def test_a_company_with_no_filings_is_reviewed_without_crashing():
    frame = prices(np.linspace(50, 100, 300))
    result = experts.review(pd.DataFrame(), {}, frame, sic=None, serious=[])
    assert result["unknown"] >= 4
    assert result["blocked"] is None


def test_altman_danger_alone_does_not_block():
    danger = experts.lens("Could it go bust?", "s", experts.BAD, "Danger.", "t")
    assert experts.block_reason([{**danger, "z": 1.0}]) is None


def test_routine_filing_warns_but_only_severe_ones_block():
    assert experts.block_reason([experts.filings_lens(["Changed its auditor"])]) is None
    severe = experts.filings_lens(["Said earlier accounts should no longer be relied on"])
    assert "serious filing" in experts.block_reason([severe])


def test_graham_number():
    report = {"metrics": [{"name": "Net income", "value": 10.0}], "equity": 50.0}
    assert experts.graham(report, 100.0)["verdict"] == experts.GOOD
    assert experts.graham(report, 1000.0)["verdict"] == experts.BAD
    assert experts.graham(report, None)["verdict"] == experts.UNKNOWN


def prices(values):
    return pd.DataFrame({"close": np.array(values, dtype=float)})


def test_trend_rules_need_a_year_of_prices():
    assert experts.trend(prices([1.0] * 50))["verdict"] == experts.UNKNOWN
    assert experts.trend(prices(np.linspace(50, 100, 300)))["verdict"] == experts.GOOD
    assert experts.trend(prices(np.linspace(100, 50, 300)))["verdict"] == experts.BAD


def test_mental_traps_fit_the_situation():
    surge = prices([100.0] * 30 + [130.0])
    names = [t["name"] for t in experts.mental_traps(surge, None, None, None)]
    assert names == ["Chasing a jump"]
    losing = {"profit": -20.0, "shares": 1.0, "buy_price": 100.0}
    names = [t["name"] for t in experts.mental_traps(prices([100.0] * 30), losing, 3, None)]
    assert names == ["Holding a loser to avoid admitting it", "Betting into results"]


def verdict_for(call, owned=False):
    return {"call": call, "reason": "r", "proven": True, "kind": "buy", "owned": owned}


def test_serious_trouble_overrides_a_buy_and_says_why():
    danger = experts.lens("Could it go bust?", "s", experts.BAD, "Danger zone.", "t")
    health = experts.lens("Health", "s", experts.MIXED, "Scores 3.", "t")
    review = {"blocked": experts.block_reason([{**health, "score": 3}, {**danger, "z": 1.0}])}
    result = advice.apply_experts(verdict_for("Buy"), review)
    assert result["call"] == "Leave alone"
    assert result["proven"] is False
    assert "danger zone" in result["reason"]
    assert advice.apply_experts(verdict_for("Keep", True), review)["call"] == "Sell"
    assert advice.apply_experts(verdict_for("Sell"), review)["call"] == "Sell"


def test_an_expensive_stock_is_not_blocked():
    pricey = experts.lens("Is it cheap?", "s", experts.BAD, "Scores 400.", "t")
    assert experts.block_reason([pricey]) is None
