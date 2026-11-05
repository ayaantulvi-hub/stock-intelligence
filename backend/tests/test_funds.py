"""Big investors. Every filing here is a TEST FIXTURE."""

from datetime import UTC, date, datetime

import pandas as pd
from sqlalchemy import text

from stockintel import forecast, queries
from stockintel.ingest import issuer_key, run_funds
from stockintel.providers.base import Provenance
from stockintel.providers.sec import parse_info_table

XML = b"""<informationTable xmlns="http://www.sec.gov/edgar/document/thirteenf/informationtable">
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><shrsOrPrnAmt><sshPrnamt>100</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><shrsOrPrnAmt><sshPrnamt>50</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt></infoTable>
<infoTable><nameOfIssuer>APPLE INC</nameOfIssuer><shrsOrPrnAmt><sshPrnamt>999</sshPrnamt>
<sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt><putCall>Call</putCall></infoTable>
</informationTable>"""


def test_table_adds_up_shares_and_leaves_out_options():
    assert parse_info_table(XML) == [{"issuer": "APPLE INC", "shares": 150.0}]


def test_issuer_names_match_across_lists():
    assert issuer_key("Apple Inc.") == issuer_key("APPLE INC")
    assert issuer_key("LAM RESEARCH CORP") == "LAM RESEARCH"


class Sec:
    def fund_filings(self, cik, since):
        return "Fixture Fund", [
            {"accession_number": f"a{cik}", "filed": date(2026, 8, 14), "period": date(2026, 6, 30)}
        ]

    def fund_holdings(self, cik, accession):
        provenance = Provenance("SEC EDGAR", "https://x.test", datetime.now(UTC), "end_of_day")
        return [{"issuer": "APPLE INC", "shares": 10.0}], "https://x.test/t.xml", provenance


def test_holdings_store_once_and_reach_the_checklist(engine):
    with engine.begin() as conn:
        security = conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('AAPL', 1, 'Apple Inc.', 'NASDAQ', 1) RETURNING id"""
            )
        ).scalar()
    now = datetime(2026, 11, 5, tzinfo=UTC)
    assert run_funds(engine, Sec(), now) == "ok"
    assert run_funds(engine, Sec(), now) == "ok"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM fund_holdings")).scalar() == 8
    assert queries.fund_check(engine, security)["topic"] == "Big investors"


def test_signal_counts_each_fund_for_a_quarter_after_filing():
    rows = pd.DataFrame(
        {
            "fund_cik": [1, 1, 2, 2],
            "period": pd.to_datetime(["2026-03-31", "2026-06-30"] * 2),
            "filed": pd.to_datetime(["2026-05-15", "2026-08-14"] * 2),
            "shares": [100.0, 150.0, 100.0, 60.0],
        }
    )
    changes = forecast.fund_changes(rows)
    days = pd.Series(pd.to_datetime(["2026-08-14", "2026-08-15", "2026-12-30"]))
    assert forecast.fund_signal(changes, days).tolist() == [0, 0, 0]
    only_up = rows[rows["fund_cik"] == 1]
    assert forecast.fund_signal(forecast.fund_changes(only_up), days).tolist() == [0, 1, 0]


def test_a_split_sized_jump_is_not_a_decision():
    rows = pd.DataFrame(
        {
            "fund_cik": [1, 1],
            "period": pd.to_datetime(["2026-03-31", "2026-06-30"]),
            "filed": pd.to_datetime(["2026-05-15", "2026-08-14"]),
            "shares": [100.0, 400.0],
        }
    )
    assert forecast.fund_changes(rows)["move"].tolist() == [0.0, 0.0]
