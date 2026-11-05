"""News from GDELT, which indexes the world's news sites and scores their tone.

Docs: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/ (free, no key, one request every
5 seconds, the latest 3 months). Only headlines and links are stored. Articles aren't copied.
"""

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance, RateLimited

URL = "https://api.gdeltproject.org/api/v2/doc/doc"
WAIT_SECONDS = 5.5
# Established outlets only, as the brief ranks news above convenience sources. Social is excluded.
DOMAINS = (
    "reuters.com",
    "bloomberg.com",
    "ft.com",
    "wsj.com",
    "cnbc.com",
    "marketwatch.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "nytimes.com",
    "economist.com",
    "barrons.com",
    "theguardian.com",
    "axios.com",
)
TOPICS = {
    "Interest rates and the Fed": '("Federal Reserve" OR "interest rates")',
    "Inflation": '(inflation OR "consumer prices")',
    "Jobs and the economy": '("jobs report" OR recession OR "economic growth")',
    "Tariffs and trade": '(tariffs OR "trade war" OR "trade deal")',
    "Government and elections": '(Congress OR "White House" OR midterms)',
    "Oil and energy": '("oil prices" OR OPEC)',
    "War and world events": "(war OR sanctions OR invasion)",
    "AI and technology": '("artificial intelligence" OR semiconductors)',
    "Banks and markets": '("Wall Street" OR banks OR "stock market")',
}
ENDINGS = re.compile(
    r"[,.]?\s+(inc|corp|corporation|co|company|plc|ltd|limited|ag|sa|nv|se|holdings?|group|"
    r"technologies|/de|/md)\.?$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Article:
    url: str
    title: str
    domain: str
    seen_at: datetime


def company_query(name: str) -> str:
    """A search for a company in financial coverage, using its everyday name."""
    plain = name.strip()
    for _ in range(4):
        plain = ENDINGS.sub("", plain).strip()
    if plain.isupper():
        plain = plain.title()
    return f'"{plain}" (shares OR stock OR earnings OR investors)'


def full_query(query: str) -> str:
    outlets = " OR ".join(f"domainis:{domain}" for domain in DOMAINS)
    return f"{query} ({outlets}) sourcelang:english"


class GdeltProvider:
    def __init__(self, client: httpx.Client | None = None, wait: float = WAIT_SECONDS):
        self.client = client or httpx.Client(timeout=45, follow_redirects=True)
        self.wait = wait

    def _get(self, query: str, mode: str, timespan: str, extra: dict | None = None) -> dict:
        time.sleep(self.wait)
        params = {
            "query": full_query(query),
            "mode": mode,
            "timespan": timespan,
            "format": "json",
            **(extra or {}),
        }
        try:
            response = self.client.get(URL, params=params)
        except httpx.HTTPError as exc:
            raise FeedError(f"GDELT: request failed ({type(exc).__name__})") from None
        if response.status_code == 429:
            raise RateLimited("GDELT: rate limit reached (HTTP 429)")
        if response.status_code != 200:
            raise FeedError(f"GDELT: HTTP {response.status_code}")
        # An empty result is an empty body. A bad query is a line of plain text.
        if not response.text.strip():
            return {}
        try:
            return response.json()
        except ValueError:
            raise FeedError(f"GDELT: {response.text[:80]}") from None

    def articles(self, query: str, timespan: str = "2d") -> tuple[list[Article], Provenance]:
        retrieved = datetime.now(UTC)
        data = self._get(query, "ArtList", timespan, {"maxrecords": 15, "sort": "DateDesc"})
        try:
            found = [
                Article(
                    row["url"],
                    row["title"],
                    row["domain"],
                    datetime.strptime(row["seendate"], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC),
                )
                for row in data.get("articles", [])
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError("GDELT: unexpected article shape") from None
        return found, Provenance("GDELT", URL, retrieved, "delayed")

    def tone(self, query: str, timespan: str = "1month") -> tuple[dict, Provenance]:
        """Average tone per day. Above zero reads positive and below zero negative."""
        retrieved = datetime.now(UTC)
        data = self._get(query, "TimelineTone", timespan)
        days: dict = {}
        try:
            for series in data.get("timeline", []):
                for point in series.get("data", []):
                    day = datetime.strptime(point["date"], "%Y%m%dT%H%M%SZ").date()
                    days.setdefault(day, []).append(float(point["value"]))
        except (KeyError, TypeError, ValueError):
            raise FeedError("GDELT: unexpected tone shape") from None
        averages = {day: sum(values) / len(values) for day, values in days.items()}
        return averages, Provenance("GDELT", URL, retrieved, "delayed")
