"""Long-term engine and company feeds. All facts here are TEST FIXTURES."""

from datetime import date

import httpx
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel import longterm, queries
from stockintel.ingest import run_facts, run_fed, run_history, run_insiders
from stockintel.providers.base import Fact, FeedError, InsiderDocument, InsiderTrade, Provenance
from stockintel.providers.fed import FedProvider, parse_page
from stockintel.providers.sec import SecProvider


def fact(tag, value, year, start=True, form="10-K", filed=None, unit="USD"):
    return {
        "tag": tag,
        "unit": unit,
        "period_start": date(year, 1, 1) if start else None,
        "period_end": date(year, 12, 31),
        "value": value,
        "accession_number": f"acc-{year}",
        "fiscal_period": "FY",
        "form": form,
        "filed": filed or date(year + 1, 2, 1),
        "document_url": f"https://fixture.test/{year}/",
    }


REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
OCF = "NetCashProvidedByUsedInOperatingActivities"
CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"


def company():
    rows = [fact(REVENUE, 100.0 * 1.1 ** (year - 2020), year) for year in range(2020, 2024)]
    rows += [
        fact("GrossProfit", 66.55, 2023),
        fact("NetIncomeLoss", 13.31, 2023),
        fact(OCF, 20.0, 2023),
        fact(CAPEX, 5.0, 2023),
        fact("Assets", 200.0, 2023, start=False),
        fact("StockholdersEquity", 100.0, 2023, start=False),
        fact("LongTermDebtNoncurrent", 50.0, 2023, start=False),
        fact("CashAndCashEquivalentsAtCarryingValue", 10.0, 2023, start=False),
        fact("EntityCommonStockSharesOutstanding", 10.0, 2023, start=False, unit="shares"),
    ]
    return pd.DataFrame(rows)


def metric(result, name):
    return next(item for item in result["metrics"] if item["name"] == name)


def test_ratios_and_growth():
    result = longterm.report(company(), price=10.0)
    assert metric(result, "Gross margin")["value"] == pytest.approx(0.5)
    assert metric(result, "Debt to equity")["value"] == pytest.approx(0.5)
    assert metric(result, "Revenue growth a year, 3 years")["value"] == pytest.approx(0.1)
    assert metric(result, "Free cash flow")["value"] == 15.0
    assert metric(result, "Free cash flow yield")["value"] == pytest.approx(0.15)


def test_every_metric_links_to_its_filing():
    result = longterm.report(company(), price=10.0)
    for item in result["metrics"]:
        assert item["sources"]
        assert all(source["url"].startswith("https://fixture.test/") for source in item["sources"])
    assert result["valuation_inputs"]


def test_quarterly_figures_are_not_read_as_a_year():
    frame = pd.DataFrame(
        [{**fact(REVENUE, 5.0, 2023), "period_start": date(2023, 10, 1)}, fact(REVENUE, 20.0, 2022)]
    )
    assert metric(longterm.report(frame, 10.0), "Revenue")["value"] == 20.0


def test_missing_figures_stay_missing():
    result = longterm.report(company()[lambda f: f["tag"] != "GrossProfit"], 10.0)
    assert metric(result, "Gross margin")["value"] is None


def test_no_facts_is_unavailable():
    assert longterm.report(pd.DataFrame(), 10.0)["available"] is False


def test_negative_cash_flow_gives_no_valuation():
    frame = company()
    frame.loc[frame["tag"] == OCF, "value"] = -1.0
    assert longterm.report(frame, 10.0)["cases"] == []


def test_dcf_matches_a_hand_calculation():
    # Growth equal to terminal: a growing perpetuity of 100 * 1.02 at 10% is 1275.
    value = longterm.discounted_value(100.0, 0.02, 0.10, 0.02, 0.0, 0.0, 1.0)
    assert value == pytest.approx(1275.0)


def test_debt_and_cash_change_value_per_share():
    base = longterm.discounted_value(100.0, 0.02, 0.10, 0.02, 0.0, 0.0, 10.0)
    assert longterm.discounted_value(100.0, 0.02, 0.10, 0.02, 50.0, 0.0, 10.0) == pytest.approx(
        base - 5
    )
    assert longterm.discounted_value(100.0, 0.02, 0.10, 0.02, 0.0, 50.0, 10.0) == pytest.approx(
        base + 5
    )


def test_cases_are_ordered_and_assumptions_can_change():
    cases = {c["name"]: c["value"] for c in longterm.report(company(), 10.0)["cases"]}
    assert cases["Bear"] < cases["Base"] < cases["Bull"]
    changed = longterm.report(company(), 10.0, {"discount_rate": 0.12})
    assert changed["assumptions"]["discount_rate"] == 0.12
    assert changed["cases"][1]["value"] < cases["Base"]


def test_discount_below_terminal_gives_no_valuation():
    assert longterm.report(company(), 10.0, {"discount_rate": 0.01})["cases"] == []


FORM_4 = b"""<ownershipDocument>
<reportingOwner><reportingOwnerId><rptOwnerName>FIXTURE PERSON</rptOwnerName></reportingOwnerId>
<reportingOwnerRelationship><officerTitle>CFO</officerTitle></reportingOwnerRelationship>
</reportingOwner><aff10b5One>true</aff10b5One>
<nonDerivativeTable><nonDerivativeTransaction>
<transactionDate><value>2026-10-27</value></transactionDate>
<transactionCoding><transactionCode>S</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>2399</value></transactionShares>
<transactionPricePerShare><value>343.36</value></transactionPricePerShare></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""


def client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_form_4_is_read():
    provider = SecProvider("a@b.test", client(lambda r: httpx.Response(200, content=FORM_4)))
    trades, _ = provider.insider_trades("https://fixture.test/form4.xml")
    assert trades[0].owner == "FIXTURE PERSON"
    assert trades[0].code == "S"
    assert trades[0].shares == 2399
    assert trades[0].price == 343.36
    assert trades[0].planned_sale is True


def test_broken_form_4_raises():
    provider = SecProvider("a@b.test", client(lambda r: httpx.Response(200, content=b"<a")))
    with pytest.raises(FeedError):
        provider.insider_trades("https://fixture.test/form4.xml")


def test_company_facts_are_parsed():
    payload = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {
                        "USD": [
                            {
                                "end": "2026-09-26",
                                "val": 5,
                                "accn": "0000320193-26-000026",
                                "fy": 2026,
                                "fp": "FY",
                                "form": "10-K",
                                "filed": "2026-11-03",
                            }
                        ]
                    }
                }
            },
            "dei": {},
        }
    }
    provider = SecProvider("a@b.test", client(lambda r: httpx.Response(200, json=payload)))
    facts, _ = provider.company_facts(320193)
    assert facts[0].tag == "Assets"
    assert facts[0].period_start is None
    assert facts[0].document_url.endswith("/320193/000032019326000026/")


PROVENANCE = Provenance(
    "SEC EDGAR", "https://fixture.test", pd.Timestamp("2026-07-01", tz="UTC"), "end_of_day"
)


class FixtureFacts:
    def company_facts(self, cik):
        row = {k: v for k, v in fact("Assets", 5.0, 2025, start=False).items()}
        return [Fact(**row), Fact(**row)], PROVENANCE


class FixtureInsiders:
    calls = 0

    def insider_documents(self, cik, since):
        return [
            InsiderDocument("a1", date(2026, 7, 1), "https://fixture.test/1.xml"),
            InsiderDocument("a2", date(2026, 7, 2), "https://fixture.test/2.xml"),
        ]

    def insider_trades(self, url):
        self.calls += 1
        return [
            InsiderTrade(0, "Fixture", None, date(2026, 7, 1), "P", 10.0, 5.0, False)
        ], PROVENANCE


@pytest.fixture
def security(engine):
    with engine.begin() as conn:
        conn.execute(
            text("""INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                    VALUES ('AAA', 1, 'Fixture', 'NYSE', 1)""")
        )
    return engine


def test_facts_feed_stores_each_fact_once(security):
    assert run_facts(security, FixtureFacts()) == "ok"
    assert run_facts(security, FixtureFacts()) == "ok"
    with security.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM company_facts")).scalar() == 1


def test_insider_feed_reads_each_document_once_within_its_limit(security):
    provider = FixtureInsiders()
    now = pd.Timestamp("2026-07-10", tz="UTC").to_pydatetime()
    assert run_insiders(security, provider, now, 1) == "ok"
    assert provider.calls == 1
    assert run_insiders(security, provider, now, 5) == "ok"
    assert provider.calls == 2
    assert run_insiders(security, provider, now, 5) == "ok"
    assert provider.calls == 2


def test_valuation_for_a_stock_with_no_facts(security):
    assert queries.valuation(security, "AAA", {})["available"] is False
    assert queries.valuation(security, "ZZZ", {}) is None


def test_net_income_and_yearly_history_are_shown():
    result = longterm.report(company(), 10.0)
    assert metric(result, "Net income")["value"] == 13.31
    assert metric(result, "Net income")["sources"]
    assert result["history"][-1]["net_income"] == 13.31
    assert result["history"][-1]["revenue"] == pytest.approx(133.1)


def quarter(tag, value, year, month, filed):
    start = date(year, month, 1)
    end = date(year, month + 2, 28)
    return {
        **fact(tag, value, year),
        "period_start": start,
        "period_end": end,
        "form": "10-Q",
        "filed": filed,
    }


def test_quarter_compares_with_the_same_quarter_a_year_before():
    frame = pd.DataFrame(
        [
            quarter("NetIncomeLoss", 10.0, 2024, 4, date(2024, 8, 1)),
            quarter("NetIncomeLoss", 15.0, 2025, 4, date(2025, 8, 1)),
            quarter(REVENUE, 100.0, 2024, 4, date(2024, 8, 1)),
            quarter(REVENUE, 110.0, 2025, 4, date(2025, 8, 1)),
        ]
    )
    table = longterm.quarterly_changes(frame)
    latest = table.iloc[-1]
    assert latest["income_q"] == pytest.approx(0.5)
    assert latest["revenue_q"] == pytest.approx(0.1)
    assert latest["available"] == pd.Timestamp("2025-08-02")


class FixtureFloats:
    def public_floats(self, year):
        return [(1, 5.0), (2, 9.0), (2, 3.0)], PROVENANCE


class FixtureFed:
    def meetings(self, first_year):
        return [date(2026, 1, 28), date(2026, 3, 18)], PROVENANCE


def test_past_sizes_are_ranked_and_stored_once(engine):
    now = pd.Timestamp("2011-06-01", tz="UTC").to_pydatetime()
    assert run_history(engine, FixtureFloats(), now) == "ok"
    assert run_history(engine, FixtureFloats(), now) == "ok"
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT cik, size_rank FROM historic_float WHERE year = 2009 ORDER BY size_rank")
        ).all()
    assert [tuple(row) for row in rows] == [(2, 1), (1, 2)]


def test_fed_dates_are_stored_once(engine):
    assert run_fed(engine, FixtureFed()) == "ok"
    assert run_fed(engine, FixtureFed()) == "ok"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fed_meetings")).scalar() == 2


def test_fed_calendar_page_is_read():
    html = """<h4>2026 FOMC Meetings</h4>
    <div><strong>December</strong></div><div class="fomc-meeting__date col-xs-4">8-9*</div>
    <a href="/newsevents/pressreleases/monetary20260128a.htm">Statement</a>"""
    assert parse_page(html) == {date(2026, 12, 9), date(2026, 1, 28)}


def test_fed_calendar_with_no_dates_is_an_error():
    provider = FedProvider(client(lambda r: httpx.Response(200, text="<html></html>")))
    with pytest.raises(FeedError):
        provider.meetings(2026)
