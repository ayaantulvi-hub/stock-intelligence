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
# Company and official announcements. Too many to sort by topic, so only names are matched,
# except official bodies, whose every release is about the whole market.
ANNOUNCEMENTS = {
    "PR Newswire": "https://www.prnewswire.com/rss/news-releases-list.rss",
}
OFFICIAL = {
    "Federal Reserve": "https://www.federalreserve.gov/feeds/press_all.xml",
    "SEC": "https://www.sec.gov/news/pressreleases.rss",
}
# Each industry: words that mark a story, and the SIC code ranges of the companies it touches.
INDUSTRIES = {
    "Chips": (r"\b(chips?|semiconductors?|foundry)\b", ((3670, 3679),)),
    "Software and internet": (r"\b(software|cloud|cybersecurity|social media)\b", ((7370, 7379),)),
    "Banks and finance": (r"\b(banks?|lenders?|mortgages?|insurers?)\b", ((6000, 6799),)),
    "Oil and gas": (r"\b(oil|crude|gas|opec|refiners?|drillers?)\b", ((1300, 1399), (2900, 2999))),
    "Drugs and health": (
        r"\b(drugs?|pharma\w*|biotech|fda|medicare|hospitals?|vaccines?)\b",
        ((2830, 2839), (3840, 3859), (8000, 8099)),
    ),
    "Retail": (r"\b(retail\w*|shoppers?|consumer spending)\b", ((5200, 5999),)),
    "Cars": (r"\b(cars?|automakers?|carmakers?|electric vehicles?|evs?)\b", ((3710, 3719),)),
    "Airlines and travel": (
        r"\b(airlines?|flights?|hotels?|cruise)\b",
        ((4500, 4599), (7000, 7099)),
    ),
    "Defence": (
        r"\b(defen[cs]e|military|weapons?|missiles?|pentagon)\b",
        ((3720, 3769), (3810, 3819)),
    ),
    "Power and utilities": (r"\b(utilit\w+|power grid|electricity|nuclear)\b", ((4900, 4999),)),
    "Metals and mining": (
        r"\b(steel|aluminum|copper|gold|lithium|mining|miners?)\b",
        ((1000, 1499), (3300, 3399)),
    ),
    "Machinery and building": (
        r"\b(construction|machinery|housing|homebuilders?)\b",
        ((1500, 1799), (3500, 3569)),
    ),
    "Food and drink": (r"\b(food|beverages?|grocers?|beef|coffee)\b", ((2000, 2099),)),
    "Telecoms and media": (
        r"\b(telecoms?|broadband|5g|streaming|broadcasters?)\b",
        ((4800, 4899),),
    ),
    "Property": (
        r"\b(real estate|landlords?|reits?|office towers?)\b",
        ((6500, 6599), (6798, 6798)),
    ),
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


def industries_of(title: str) -> list[str]:
    return [
        f"Industry: {name}"
        for name, (words, _) in INDUSTRIES.items()
        if re.search(words, title, re.IGNORECASE)
    ]


def industry_of(sic: int | None) -> str | None:
    """Which news group a company belongs to, from its official SEC industry code."""
    if sic is None:
        return None
    for name, (_, ranges) in INDUSTRIES.items():
        if any(low <= sic <= high for low, high in ranges):
            return f"Industry: {name}"
    return None


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

    def feed(
        self, source: str, url: str, headers: dict | None = None
    ) -> tuple[list[Headline], Provenance]:
        retrieved = datetime.now(UTC)
        try:
            response = self.client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            raise FeedError(f"{source}: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"{source}: HTTP {response.status_code}")
        return (
            parse_feed(response.text, source),
            Provenance("Publisher news feeds", url, retrieved, "delayed"),
        )
