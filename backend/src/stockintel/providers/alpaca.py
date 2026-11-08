"""Alpaca 1-minute bars from the free IEX feed.

Docs: https://docs.alpaca.markets/docs/about-market-data-api and the market data FAQ. The free
plan gives real-time IEX data and history back to 2016, at 200 requests a minute. The
15-minute delay on history applies to the paid SIP feed only. IEX is a small share of all
trading, so a minute's high or low can differ from consolidated prices.
"""

from datetime import UTC, datetime

import httpx
import pandas as pd

from stockintel.providers.base import FeedError, Provenance
from stockintel.providers.http import get_json

BARS = "https://data.alpaca.markets/v2/stocks/bars"


class AlpacaProvider:
    def __init__(self, key_id: str, secret: str, client: httpx.Client | None = None):
        if not key_id or not secret:
            raise FeedError("Alpaca: ALPACA_API_KEY_ID and ALPACA_API_SECRET_KEY are not set")
        self.client = client or httpx.Client(timeout=30)
        # Keys travel in headers, so stored source URLs contain no secret.
        self.headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret}

    def minute_bars(
        self, symbols: tuple[str, ...], start: datetime, end: datetime, timeframe: str = "1Min"
    ) -> tuple[dict[str, pd.DataFrame], Provenance]:
        params = {
            "symbols": ",".join(symbols),
            "timeframe": timeframe,
            "start": start.astimezone(UTC).isoformat(),
            "end": end.astimezone(UTC).isoformat(),
            "feed": "iex",
            "adjustment": "split",
            "limit": 10000,
        }
        rows: dict[str, list] = {symbol: [] for symbol in symbols}
        while True:
            data = get_json(self.client, BARS, "Alpaca bars", params=params, headers=self.headers)
            if not isinstance(data, dict):
                raise FeedError("Alpaca bars: expected an object")
            for symbol, bars in (data.get("bars") or {}).items():
                rows.setdefault(symbol, []).extend(bars)
            token = data.get("next_page_token")
            if not token:
                break
            params["page_token"] = token
        frames = {}
        for symbol, bars in rows.items():
            try:
                frame = pd.DataFrame(
                    {
                        "time": pd.to_datetime([b["t"] for b in bars], utc=True),
                        "open": [float(b["o"]) for b in bars],
                        "high": [float(b["h"]) for b in bars],
                        "low": [float(b["l"]) for b in bars],
                        "close": [float(b["c"]) for b in bars],
                        "volume": [float(b["v"]) for b in bars],
                    }
                )
            except (KeyError, TypeError, ValueError):
                raise FeedError("Alpaca bars: a bar is missing a value") from None
            frame["time"] = frame["time"].dt.tz_convert("America/New_York")
            frames[symbol] = frame.sort_values("time").reset_index(drop=True)
        provenance = Provenance("Alpaca (IEX)", BARS, datetime.now(UTC), "live")
        return frames, provenance
