"""Headlines from publishers' public RSS feeds, for one person's private reading.

Only the headline and link are stored, as any feed reader does. Articles aren't copied. If a
feed fails or moves, the others carry on and the failure is reported.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from stockintel.providers.base import FeedError, Provenance

FEEDS = {
    "BBC": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "CNBC": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Economy": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "CNBC Earnings": "https://www.cnbc.com/id/15839135/device/rss/rss.html",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "New York Times": "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    "The Guardian": "https://www.theguardian.com/uk/business/rss",
    "Financial Times": "https://www.ft.com/markets?format=rss",
}
TOPICS = {
    "Interest rates and the Fed": r"\b(fed|federal reserve|interest rates?|powell|rate cuts?)\b",
    "Inflation": r"\b(inflation|consumer prices|cpi)\b",
    "Jobs and the economy": r"\b(jobs|payrolls|unemployment|recession|gdp|economy)\b",
    "Tariffs and trade": r"\b(tariffs?|trade war|trade deal|duties|exports?)\b",
    "Government and elections": r"\b(congress|white house|senate|midterms?|election|president)\b",
    "Oil and energy": r"\b(oil|opec|crude|gas prices|energy)\b",
    "War and world events": r"\b(war|sanctions?|invasion|strikes?|ukraine|russia|iran|china)\b",
    "AI and technology": r"\b(ai|artificial intelligence|chips?|semiconductors?|nvidia)\b",
    "Banks and markets": r"\b(wall street|banks?|stocks?|markets?|s&p 500|nasdaq|dow)\b",
}
ENDINGS = re.compile(
    r"[,.]?\s+(inc|corp|corporation|co|company|plc|ltd|limited|ag|sa|nv|se|holdings?|group|"
    r"technologies|/de|/md|/new)\.?$",
    re.IGNORECASE,
)
# Everyday words that are also company names, which need a business word nearby.
COMMON_NAMES = {
    "Target",
    "Block",
    "Match",
    "Gap",
    "Ball",
    "Fox",
    "Shell",
    "Visa",
    "Apple",
    "Oracle",
}
BUSINESS = re.compile(
    r"\b(shares?|stock|earnings|profit|sales|revenue|ceo|deal|investors?)\b", re.IGNORECASE
)
GOOD_WORDS = re.compile(
    r"\b(beats?|gains?|rises?|surges?|soars?|jumps?|rally|rallies|record|growth|upgrade[sd]?|"
    r"strong|profit|boost)\b",
    re.IGNORECASE,
)
BAD_WORDS = re.compile(
    r"\b(miss(es)?|falls?|drops?|plunges?|slumps?|sinks?|tumbles?|cuts?|loss(es)?|weak|lawsuit|"
    r"probe|fraud|layoffs?|warns?|downgrade[sd]?|bankrupt\w*|fears?|crisis)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Headline:
    url: str
    title: str
    domain: str
    seen_at: datetime


def plain_name(name: str) -> str:
    plain = name.strip()
    for _ in range(4):
        plain = ENDINGS.sub("", plain).strip()
    return plain.title() if plain.isupper() else plain


def matches_company(name: str, title: str) -> bool:
    if len(name) < 4 or not re.search(rf"\b{re.escape(name)}\b", title):
        return False
    return name not in COMMON_NAMES or bool(BUSINESS.search(title))


def topics_of(title: str) -> list[str]:
    return [name for name, words in TOPICS.items() if re.search(words, title, re.IGNORECASE)]


def headline_mood(title: str) -> int:
    """A rough count: positive words minus negative ones. It can't read meaning."""
    return len(GOOD_WORDS.findall(title)) - len(BAD_WORDS.findall(title))


def parse_feed(xml: str, source: str) -> list[Headline]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        raise FeedError(f"{source}: not a valid feed") from None
    found = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = item.findtext("pubDate")
        if not title or not link.startswith("http") or not published:
            continue
        try:
            when = parsedate_to_datetime(published).astimezone(UTC)
        except (TypeError, ValueError):
            continue
        found.append(Headline(link, title, source, when))
    return found


class NewsProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": "stock-intelligence"}
        )

    def feed(self, source: str, url: str) -> tuple[list[Headline], Provenance]:
        retrieved = datetime.now(UTC)
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise FeedError(f"{source}: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"{source}: HTTP {response.status_code}")
        return (
            parse_feed(response.text, source),
            Provenance("Publisher news feeds", url, retrieved, "delayed"),
        )
