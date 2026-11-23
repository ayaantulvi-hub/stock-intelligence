"""SEC EDGAR. Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

The SEC allows 10 requests a second and requires a User-Agent with a contact email. The Quant
Lab uses three things from it: the list of listed companies, each company's industry code, and
each year's reported public float (to rebuild which companies were large at the time).
"""

import time
from datetime import UTC, datetime

import httpx

from stockintel.providers.base import FeedError, Listing, Provenance
from stockintel.providers.http import get_json

TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
FLOAT_URL = "https://data.sec.gov/api/xbrl/frames/dei/EntityPublicFloat/USD/CY{year}Q2I.json"
MIN_SECONDS_BETWEEN_REQUESTS = 0.15


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

    def industry(self, cik: int) -> int | None:
        """The company's Standard Industrial Classification code, or None if it has none."""
        data = self._get(SUBMISSIONS_URL.format(cik=cik), f"SEC CIK {cik}")
        try:
            sic = data.get("sic")
            return int(sic) if sic else None
        except (AttributeError, TypeError, ValueError):
            raise FeedError(f"SEC CIK {cik}: unexpected response shape") from None

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
