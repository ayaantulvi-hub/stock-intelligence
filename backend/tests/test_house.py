"""House trade reports. The text is a real public report (Filing ID 20035143), kept as a
TEST FIXTURE, copied from day-trader-skill's tests (MIT licence)."""

from datetime import date
from pathlib import Path

from stockintel.providers import house

TEXT = (Path(__file__).parent / "fixtures/house/ptr-20035143.txt").read_text()


def test_reads_each_trade_line_with_ticker_owner_and_range():
    rows = house.parse_report(TEXT, date(2026, 8, 21))
    first = rows[0]
    assert first["ticker"] == "BE"
    assert first["owner"] == "Spouse"
    assert first["action"] == "Buy"
    assert first["trade_date"] == date(2026, 7, 24)
    assert first["amount"] == "$1,000,001 - $5,000,000"
    assert first["kind"] == "ST"
    assert first["days_to_file"] == 28
    assert rows[1]["kind"] == "OP"
    assert all(row["trade_date"] is not None for row in rows)


def test_index_keeps_only_trade_reports():
    xml = b"""<FinancialDisclosure>
      <Member><Last>Pelosi</Last><First>Nancy</First><FilingType>P</FilingType>
        <FilingDate>8/21/2026</FilingDate><DocID>20035143</DocID><Year>2026</Year></Member>
      <Member><Last>Doe</Last><First>Jane</First><FilingType>O</FilingType>
        <FilingDate>5/15/2026</FilingDate><DocID>1</DocID><Year>2026</Year></Member>
    </FinancialDisclosure>"""
    reports = house.parse_index(xml, 2026)
    assert [r.doc_id for r in reports] == ["20035143"]
    assert reports[0].filed == date(2026, 8, 21)
    assert reports[0].url.endswith("/ptr-pdfs/2026/20035143.pdf")
