"""Federal Reserve meeting dates, read from its official calendar pages."""

import re
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance

CURRENT = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
HISTORIC = "https://www.federalreserve.gov/monetarypolicy/fomchistorical{year}.htm"
STATEMENT = re.compile(r"monetary(\d{8})a\.htm")
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
SECTION = re.compile(r"(\d{4}) FOMC Meetings")
MEETING = re.compile(
    rf"<strong>\s*({MONTHS})(?:/[A-Za-z]+)?\s*</strong>.{{0,300}}?fomc-meeting__date[^>]*>\s*"
    r"(?:\d{1,2}-)?(\d{1,2})",
    re.DOTALL,
)
NUMBERS = {name: i for i, name in enumerate(MONTHS.split("|"), 1)}


def parse_page(html: str) -> set[date]:
    """Past decisions from statement links, and future dates from the meeting table."""
    days = {datetime.strptime(item, "%Y%m%d").date() for item in STATEMENT.findall(html)}
    marks = [(match.start(), int(match.group(1))) for match in SECTION.finditer(html)]
    for match in MEETING.finditer(html):
        years = [year for start, year in marks if start < match.start()]
        if years:
            days.add(date(years[-1], NUMBERS[match.group(1)], int(match.group(2))))
    return days


class FedProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=30, follow_redirects=True)

    def _page(self, url: str) -> str:
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise FeedError(f"Fed calendar: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"Fed calendar: HTTP {response.status_code}")
        return response.text

    def meetings(self, first_year: int) -> tuple[list[date], Provenance]:
        retrieved = datetime.now(UTC)
        days = parse_page(self._page(CURRENT))
        if not days:
            raise FeedError("Fed calendar: no dates found on the page")
        for year in range(first_year, min(days).year):
            days |= parse_page(self._page(HISTORIC.format(year=year)))
        return sorted(days), Provenance("Federal Reserve", CURRENT, retrieved, "end_of_day")
