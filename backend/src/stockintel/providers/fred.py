"""FRED economic data. Docs: https://fred.stlouisfed.org/docs/api/fred/series_observations.html

Requests every past version of each value, so history shows what was known at the time.
"""

from datetime import UTC, date, datetime
from urllib.parse import urlencode

import httpx

from stockintel.providers.base import FeedError, Observation, Provenance
from stockintel.providers.http import get_json

BASE = "https://api.stlouisfed.org/fred/series/observations"


class FredProvider:
    def __init__(self, api_key: str, client: httpx.Client | None = None):
        if not api_key:
            raise FeedError("FRED: FRED_API_KEY is not set")
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=60)

    def observations(self, series_id: str, start: date) -> tuple[list[Observation], Provenance]:
        query = {
            "series_id": series_id,
            "observation_start": start.isoformat(),
            "realtime_start": "1776-07-04",
            "realtime_end": "9999-12-31",
            "file_type": "json",
        }
        url = f"{BASE}?{urlencode({**query, 'api_key': self.api_key})}"
        data = get_json(self.client, url, f"FRED {series_id}")
        retrieved = datetime.now(UTC)
        try:
            observations = [
                Observation(
                    observation_date=date.fromisoformat(row["date"]),
                    realtime_start=date.fromisoformat(row["realtime_start"]),
                    # FRED writes "." when it has no value. Stored as missing, never filled.
                    value=None if row["value"] == "." else float(row["value"]),
                )
                for row in data["observations"]
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"FRED {series_id}: unexpected response shape") from None
        safe_url = f"{BASE}?{urlencode(query)}"
        return observations, Provenance("FRED", safe_url, retrieved, "end_of_day")
