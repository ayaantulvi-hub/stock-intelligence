"""FINRA consolidated short interest: shares sold short in each stock, twice a month.

Docs: https://developer.finra.org/docs (Query API) and the dataset's metadata at
https://api.finra.org/metadata/group/otcmarket/name/consolidatedShortInterestMock.
The dataset is public: no key is needed. Data covers one rolling year.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"
PAGE = 5000


@dataclass(frozen=True)
class ShortInterest:
    symbol: str
    settlement_date: date
    short_shares: float
    previous_short_shares: float | None
    avg_daily_volume: float | None
    days_to_cover: float | None


def _number(value):
    return None if value in (None, "") else float(value)


class FinraProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=60)

    def short_interest(
        self, symbols: list[str], start: date, end: date
    ) -> tuple[list[ShortInterest], Provenance]:
        rows, offset = [], 0
        while True:
            body = {
                "limit": PAGE,
                "offset": offset,
                "dateRangeFilters": [
                    {
                        "fieldName": "settlementDate",
                        "startDate": start.isoformat(),
                        "endDate": end.isoformat(),
                    }
                ],
                "domainFilters": [{"fieldName": "symbolCode", "values": symbols}],
            }
            try:
                response = self.client.post(URL, json=body, headers={"Accept": "application/json"})
            except httpx.HTTPError as exc:
                raise FeedError(f"FINRA: request failed ({type(exc).__name__})") from None
            if response.status_code == 204:
                break
            if response.status_code != 200:
                raise FeedError(f"FINRA: HTTP {response.status_code}")
            try:
                page = response.json()
            except ValueError:
                raise FeedError("FINRA: response was not valid JSON") from None
            if not isinstance(page, list):
                raise FeedError("FINRA: expected a list of records")
            for item in page:
                try:
                    rows.append(
                        ShortInterest(
                            symbol=item["symbolCode"],
                            settlement_date=date.fromisoformat(item["settlementDate"]),
                            short_shares=float(item["currentShortPositionQuantity"]),
                            previous_short_shares=_number(
                                item.get("previousShortPositionQuantity")
                            ),
                            avg_daily_volume=_number(item.get("averageDailyVolumeQuantity")),
                            days_to_cover=_number(item.get("daysToCoverQuantity")),
                        )
                    )
                except (KeyError, TypeError, ValueError):
                    raise FeedError("FINRA: a record is missing a value") from None
            if len(page) < PAGE:
                break
            offset += PAGE
        return rows, Provenance("FINRA", URL, datetime.now(UTC), "end_of_day")
