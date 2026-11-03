"""SEC EDGAR. Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

The SEC allows 10 requests a second and requires a User-Agent with a contact email.
"""

import time
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import (
    Fact,
    FeedError,
    Filing,
    InsiderDocument,
    InsiderTrade,
    Listing,
    Provenance,
)
from stockintel.providers.http import get_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "20-F", "20-F/A", "40-F", "6-K"}
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ACCESSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
FACT_TAGS = {
    "us-gaap": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "GrossProfit",
        "NetIncomeLoss",
        "Assets",
        "Liabilities",
        "StockholdersEquity",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "CashAndCashEquivalentsAtCarryingValue",
    ),
    "dei": ("EntityCommonStockSharesOutstanding",),
}
MIN_SECONDS_BETWEEN_REQUESTS = 0.15


def _text(node: ET.Element, path: str) -> str | None:
    found = node.find(path)
    return found.text.strip() if found is not None and found.text else None


def _optional_date(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


class SecProvider:
    def __init__(self, contact_email: str, client: httpx.Client | None = None):
        if not contact_email:
            raise FeedError("SEC: SEC_CONTACT_EMAIL is not set")
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"User-Agent": f"stock-intelligence {contact_email}"}
        self.last_request = 0.0

    def _get(self, url: str, name: str) -> object:
        wait = self.last_request + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        return get_json(self.client, url, name, headers=self.headers)

    def listings(self) -> tuple[list[Listing], Provenance]:
        data = self._get(TICKERS_URL, "SEC tickers")
        retrieved = datetime.now(UTC)
        try:
            rows = [dict(zip(data["fields"], row, strict=True)) for row in data["data"]]
            listings = [
                Listing(row["ticker"], int(row["cik"]), row["name"], row["exchange"] or "")
                for row in rows
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError("SEC tickers: unexpected response shape") from None
        return listings, Provenance("SEC EDGAR", TICKERS_URL, retrieved, "end_of_day")

    def filings(self, cik: int) -> tuple[list[Filing], Provenance]:
        url = SUBMISSIONS_URL.format(cik=cik)
        data = self._get(url, f"SEC CIK {cik}")
        retrieved = datetime.now(UTC)
        try:
            recent = data["filings"]["recent"]
            rows = zip(
                recent["accessionNumber"],
                recent["form"],
                recent["filingDate"],
                recent["reportDate"],
                recent["acceptanceDateTime"],
                recent["primaryDocument"],
                strict=True,
            )
            filings = [
                Filing(
                    accession_number=accession,
                    form=form,
                    filing_date=date.fromisoformat(filed),
                    report_date=_optional_date(report),
                    accepted_at=datetime.fromisoformat(accepted) if accepted else None,
                    document_url=ARCHIVE_URL.format(
                        cik=cik, accession=accession.replace("-", ""), document=document
                    ),
                )
                for accession, form, filed, report, accepted, document in rows
                if form in FORMS
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC CIK {cik}: unexpected response shape") from None
        return filings, Provenance("SEC EDGAR", url, retrieved, "end_of_day")

    def company_facts(self, cik: int) -> tuple[list[Fact], Provenance]:
        url = FACTS_URL.format(cik=cik)
        data = self._get(url, f"SEC facts CIK {cik}")
        retrieved = datetime.now(UTC)
        facts = []
        try:
            for taxonomy, tags in FACT_TAGS.items():
                concepts = data["facts"].get(taxonomy, {})
                for tag in tags:
                    for unit, rows in concepts.get(tag, {}).get("units", {}).items():
                        for row in rows:
                            accession = row["accn"]
                            facts.append(
                                Fact(
                                    tag=tag,
                                    unit=unit,
                                    period_start=_optional_date(row.get("start", "")),
                                    period_end=date.fromisoformat(row["end"]),
                                    value=float(row["val"]),
                                    accession_number=accession,
                                    fiscal_period=row.get("fp"),
                                    form=row["form"],
                                    filed=date.fromisoformat(row["filed"]),
                                    document_url=ACCESSION_URL.format(
                                        cik=cik, accession=accession.replace("-", "")
                                    ),
                                )
                            )
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC facts CIK {cik}: unexpected response shape") from None
        return facts, Provenance("SEC EDGAR", url, retrieved, "end_of_day")

    def insider_documents(self, cik: int, since: date) -> list[InsiderDocument]:
        data = self._get(SUBMISSIONS_URL.format(cik=cik), f"SEC CIK {cik}")
        try:
            recent = data["filings"]["recent"]
            rows = zip(
                recent["accessionNumber"],
                recent["form"],
                recent["filingDate"],
                recent["primaryDocument"],
                strict=True,
            )
            return [
                InsiderDocument(
                    accession,
                    date.fromisoformat(filed),
                    ARCHIVE_URL.format(
                        cik=cik,
                        accession=accession.replace("-", ""),
                        # The listed path is a styled view. The raw XML sits beside it.
                        document=document.rsplit("/", 1)[-1],
                    ),
                )
                for accession, form, filed, document in rows
                if form == "4" and date.fromisoformat(filed) >= since
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC CIK {cik}: unexpected response shape") from None

    def insider_trades(self, url: str) -> tuple[list[InsiderTrade], Provenance]:
        wait = self.last_request + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        try:
            response = self.client.get(url, headers=self.headers)
        except httpx.HTTPError as exc:
            raise FeedError(f"SEC Form 4: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"SEC Form 4: HTTP {response.status_code}")
        retrieved = datetime.now(UTC)
        try:
            root = ET.fromstring(response.content)
            owner = _text(root, "reportingOwner/reportingOwnerId/rptOwnerName") or "Unknown"
            title = _text(root, "reportingOwner/reportingOwnerRelationship/officerTitle")
            planned = (_text(root, "aff10b5One") or "").lower() in {"1", "true"}
            trades = []
            for line, row in enumerate(root.findall("nonDerivativeTable/nonDerivativeTransaction")):
                price = _text(row, "transactionAmounts/transactionPricePerShare/value")
                trades.append(
                    InsiderTrade(
                        line=line,
                        owner=owner,
                        title=title,
                        transaction_date=date.fromisoformat(
                            _text(row, "transactionDate/value")[:10]
                        ),
                        code=_text(row, "transactionCoding/transactionCode"),
                        shares=float(_text(row, "transactionAmounts/transactionShares/value")),
                        price=float(price) if price else None,
                        planned_sale=planned,
                    )
                )
        except (ET.ParseError, TypeError, ValueError):
            raise FeedError("SEC Form 4: could not read the document") from None
        return trades, Provenance("SEC EDGAR", url, retrieved, "end_of_day")
