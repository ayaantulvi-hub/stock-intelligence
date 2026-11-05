"""Tiingo end-of-day prices. Docs: https://www.tiingo.com/documentation/end-of-day"""

from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, PriceBar, Provenance, Quote
from stockintel.providers.http import get_json

BASE = "https://api.tiingo.com/tiingo/daily"
IEX = "https://api.tiingo.com/iex"
FIELDS = ("open", "high", "low", "close", "volume", "divCash", "splitFactor")


class TiingoProvider:
    def __init__(self, token: str, client: httpx.Client | None = None):
        if not token:
            raise FeedError("Tiingo: TIINGO_API_TOKEN is not set")
        # The token travels in a header, so stored source URLs contain no secret.
        self.client = client or httpx.Client(timeout=30)
        self.headers = {"Authorization": f"Token {token}"}

    def quotes(self, tickers: tuple[str, ...]) -> tuple[list[Quote], Provenance]:
        """Latest prices in one request. Docs: https://www.tiingo.com/documentation/iex"""
        url = f"{IEX}?tickers={','.join(item.lower() for item in tickers)}"
        rows = get_json(self.client, url, "Tiingo quotes", headers=self.headers)
        if not isinstance(rows, list):
            raise FeedError("Tiingo quotes: expected a list")
        retrieved = datetime.now(UTC)
        try:
            quotes = [
                Quote(
                    row["ticker"].upper(),
                    datetime.fromisoformat(row["timestamp"]),
                    float(row["tngoLast"]),
                    float(row["prevClose"]),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError("Tiingo quotes: a price is missing") from None
        return quotes, Provenance("Tiingo", url, retrieved, "delayed")

    def daily_bars(self, ticker: str, start: date, end: date) -> tuple[list[PriceBar], Provenance]:
        url = f"{BASE}/{ticker.lower()}/prices?startDate={start}&endDate={end}&format=json"
        rows = get_json(self.client, url, f"Tiingo {ticker}", headers=self.headers)
        if not isinstance(rows, list):
            raise FeedError(f"Tiingo {ticker}: expected a list of bars")
        retrieved = datetime.now(UTC)
        try:
            bars = [
                PriceBar(
                    market_date=date.fromisoformat(row["date"][:10]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    div_cash=float(row["divCash"]),
                    split_factor=float(row["splitFactor"]),
                )
                for row in rows
            ]
        except (KeyError, TypeError, ValueError):
            raise FeedError(f"Tiingo {ticker}: bar missing a required field") from None
        return bars, Provenance("Tiingo", url, retrieved, "end_of_day")
