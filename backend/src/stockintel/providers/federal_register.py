"""Presidential actions from the Federal Register, the US government's official journal.

Docs: https://www.federalregister.gov/developers/documentation/api/v1 (no key needed).
"""

import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance
from stockintel.providers.http import get_json

URL = "https://www.federalregister.gov/api/v1/documents.json"
FIELDS = ("document_number", "title", "publication_date", "html_url", "presidential_document_type")
# Plain keywords, shown as a topic only. Ceremonial proclamations match none of these.
TOPICS = (
    ("Trade and tariffs", r"tariff|duties|duty|import|trade|steel|aluminum|semiconductor"),
    ("Energy", r"energy|oil|gas|coal|nuclear|electric|pipeline|mineral"),
    ("Health and drugs", r"health|drug|pharma|medic"),
    ("Technology", r"artificial intelligence|digital|crypto|cyber|technolog"),
    ("Defence", r"defense|defence|military|armed forces|national security"),
    ("Banks and finance", r"bank|financ|credit|retirement|debt"),
    ("Sanctions", r"sanction|blocking property|emergency with respect"),
)


@dataclass(frozen=True)
class PolicyDocument:
    document_number: str
    kind: str
    title: str
    published: date
    topic: str | None
    url: str


def topic_of(title: str) -> str | None:
    lowered = title.lower()
    return next((name for name, words in TOPICS if re.search(words, lowered)), None)


class FederalRegisterProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(
            timeout=30, follow_redirects=True, headers={"User-Agent": "stock-intelligence"}
        )

    def documents(self, start: date, end: date) -> tuple[list[PolicyDocument], Provenance]:
        """Executive orders and proclamations published between two dates."""
        retrieved = datetime.now(UTC)
        found, page = [], 1
        while True:
            params = [
                ("conditions[type][]", "PRESDOCU"),
                ("conditions[publication_date][gte]", start.isoformat()),
                ("conditions[publication_date][lte]", end.isoformat()),
                ("per_page", 1000),
                ("page", page),
                ("order", "oldest"),
                *[("fields[]", field) for field in FIELDS],
            ]
            data = get_json(self.client, URL, "Federal Register", params=params)
            try:
                for row in data.get("results", []):
                    kind = row.get("presidential_document_type")
                    if kind not in ("Executive Order", "Proclamation"):
                        continue
                    found.append(
                        PolicyDocument(
                            row["document_number"],
                            kind,
                            row["title"],
                            date.fromisoformat(row["publication_date"]),
                            topic_of(row["title"]),
                            row["html_url"],
                        )
                    )
                pages = int(data.get("total_pages") or 1)
            except (AttributeError, KeyError, TypeError, ValueError):
                raise FeedError("Federal Register: unexpected response shape") from None
            if page >= pages:
                break
            page += 1
            time.sleep(0.5)
        return found, Provenance("Federal Register", URL, retrieved, "end_of_day")
