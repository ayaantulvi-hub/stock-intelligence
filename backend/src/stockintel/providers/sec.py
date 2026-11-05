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
    NotAvailable,
    Provenance,
)
from stockintel.providers.http import get_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "20-F", "20-F/A", "40-F", "6-K"}
FLOAT_URL = "https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/CY{year}Q2I.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
ACCESSION_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/"
FACT_TAGS = {
    "us-gaap": (
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "RevenuesNetOfInterestExpense",
        "Revenues",
        "SalesRevenueNet",
        "RegulatedAndUnregulatedOperatingRevenue",
        "InterestIncomeExpenseNet",
        "NoninterestIncome",
        "GrossProfit",
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "Assets",
        "AssetsCurrent",
        "Liabilities",
        "LiabilitiesCurrent",
        "RetainedEarningsAccumulatedDeficit",
        "OperatingIncomeLoss",
        "StockholdersEquity",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "CashAndCashEquivalentsAtCarryingValue",
    ),
    "ifrs-full": (
        "Revenue",
        "RevenueAndOperatingIncome",
        "RevenueFromSaleOfGoods",
        "RevenueFromContractsWithCustomers",
        "InterestRevenueExpense",
        "GrossProfit",
        "ProfitLoss",
        "Assets",
        "CurrentAssets",
        "Liabilities",
        "CurrentLiabilities",
        "RetainedEarnings",
        "ProfitLossFromOperatingActivities",
        "Equity",
        "CashFlowsFromUsedInOperatingActivities",
        "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
        "CashAndCashEquivalents",
        "NoncurrentBorrowings",
    ),
    "dei": ("EntityCommonStockSharesOutstanding",),
}
# A new holding company took over, so its filing history sits under the old number.
PREDECESSORS = {2115436: 34088}
MIN_SECONDS_BETWEEN_REQUESTS = 0.15


def parse_info_table(content: bytes) -> list[dict]:
    """Shares held per issuer from a 13F table, whatever XML namespace it declares."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        raise FeedError("SEC fund table: could not read the document") from None
    totals: dict[str, float] = {}

    def child(node, name):
        return next((item for item in node.iter() if item.tag.endswith(name)), None)

    for row in root:
        name, amount = child(row, "nameOfIssuer"), child(row, "sshPrnamt")
        if name is None or amount is None or child(row, "putCall") is not None:
            continue
        kind = child(row, "sshPrnamtType")
        if kind is not None and (kind.text or "").strip() != "SH":
            continue
        try:
            issuer = (name.text or "").strip().upper()
            totals[issuer] = totals.get(issuer, 0.0) + float(amount.text)
        except (TypeError, ValueError):
            raise FeedError("SEC fund table: a share count is unreadable") from None
    return [{"issuer": issuer, "shares": shares} for issuer, shares in totals.items()]


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
        self.sic: dict[int, int] = {}

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
            if data.get("sic"):
                self.sic[cik] = int(data["sic"])
            recent = data["filings"]["recent"]
            rows = zip(
                recent["accessionNumber"],
                recent["form"],
                recent["filingDate"],
                recent["reportDate"],
                recent["acceptanceDateTime"],
                recent["primaryDocument"],
                recent.get("items") or [""] * len(recent["form"]),
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
                    items=items or None,
                )
                for accession, form, filed, report, accepted, document, items in rows
                if form in FORMS
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC CIK {cik}: unexpected response shape") from None
        return filings, Provenance("SEC EDGAR", url, retrieved, "end_of_day")

    def public_floats(self, year: int) -> tuple[list[tuple[int, float]], Provenance]:
        """Each filer's reported market value of public shares, mid-year."""
        url = FLOAT_URL.format(year=year)
        data = self._get(url, f"SEC floats {year}")
        retrieved = datetime.now(UTC)
        try:
            rows = [(int(row["cik"]), float(row["val"])) for row in data["data"]]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC floats {year}: unexpected response shape") from None
        return rows, Provenance("SEC EDGAR", url, retrieved, "end_of_day")

    def company_facts(self, cik: int) -> tuple[list[Fact], Provenance]:
        """A company's figures, including any earlier company it replaced."""
        facts, provenance = self._company_facts(cik)
        if cik in PREDECESSORS:
            earlier, _ = self._company_facts(PREDECESSORS[cik])
            facts = earlier + facts
        return facts, provenance

    def _company_facts(self, cik: int) -> tuple[list[Fact], Provenance]:
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

    def fund_filings(self, cik: int, since: date) -> tuple[str, list[dict]]:
        """A fund's name and its quarterly holdings reports."""
        data = self._get(SUBMISSIONS_URL.format(cik=cik), f"SEC fund {cik}")
        try:
            recent = data["filings"]["recent"]
            rows = zip(
                recent["accessionNumber"],
                recent["form"],
                recent["filingDate"],
                recent["reportDate"],
                strict=True,
            )
            found = [
                {
                    "accession_number": accession,
                    "filed": date.fromisoformat(filed),
                    "period": date.fromisoformat(period),
                }
                for accession, form, filed, period in rows
                if form == "13F-HR" and date.fromisoformat(filed) >= since
            ]
            return data["name"], found
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"SEC fund {cik}: unexpected response shape") from None

    def fund_holdings(self, cik: int, accession: str) -> tuple[list[dict], str, Provenance]:
        """Shares held per issuer. Options are left out, because they aren't shares owned."""
        folder = ACCESSION_URL.format(cik=cik, accession=accession.replace("-", ""))
        listing = self._get(f"{folder}index.json", f"SEC fund {cik}")
        try:
            names = [item["name"] for item in listing["directory"]["item"]]
        except (KeyError, TypeError):
            raise FeedError(f"SEC fund {cik}: unexpected folder shape") from None
        tables = [n for n in names if n.endswith(".xml") and n != "primary_doc.xml"]
        if not tables:
            raise NotAvailable(f"SEC fund {cik}: no holdings table in this filing")
        url = f"{folder}{tables[0]}"
        wait = self.last_request + MIN_SECONDS_BETWEEN_REQUESTS - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.last_request = time.monotonic()
        try:
            response = self.client.get(url, headers=self.headers)
        except httpx.HTTPError as exc:
            raise FeedError(f"SEC fund table: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"SEC fund table: HTTP {response.status_code}")
        retrieved = datetime.now(UTC)
        return (
            parse_info_table(response.content),
            url,
            Provenance("SEC EDGAR", url, retrieved, "end_of_day"),
        )

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
