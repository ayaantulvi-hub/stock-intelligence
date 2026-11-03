"""SEC EDGAR. Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

The SEC allows 10 requests a second and requires a User-Agent with a contact email.
"""

import time
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Filing, Listing, Provenance
from stockintel.providers.http import get_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
FORMS = {"10-K", "10-K/A", "10-Q", "10-Q/A", "8-K", "8-K/A", "20-F", "20-F/A", "40-F", "6-K"}
MIN_SECONDS_BETWEEN_REQUESTS = 0.15


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
