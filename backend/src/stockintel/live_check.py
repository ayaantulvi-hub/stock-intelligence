"""Check that each live service answers. Prints statuses only, never secrets or data values."""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

from sqlalchemy import create_engine, text

from stockintel.config import Settings


def fetch(url: str, headers: dict[str, str] | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "stock-intelligence", **(headers or {})}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def check_database() -> str:
    with create_engine(Settings().database_url).connect() as conn:
        conn.execute(text("SELECT 1"))
    return "ok"


def check_tiingo() -> str:
    token = urllib.parse.urlencode({"token": os.environ["TIINGO_API_TOKEN"]})
    status, body = fetch(f"https://api.tiingo.com/tiingo/daily/aapl?{token}")
    return "ok" if status == 200 and json.loads(body).get("ticker") else f"http {status}"


def check_tiingo_delisted() -> str:
    """Lehman Brothers left the market in 2008, so a result proves delisted coverage."""
    token = urllib.parse.urlencode({"token": os.environ["TIINGO_API_TOKEN"]})
    status, body = fetch(f"https://api.tiingo.com/tiingo/daily/lehmq?{token}")
    if status != 200:
        return f"http {status}"
    meta = json.loads(body)
    return f"covered, endDate {meta.get('endDate')}"


def check_sec() -> str:
    agent = f"stock-intelligence {os.environ['SEC_CONTACT_EMAIL']}"
    url = "https://data.sec.gov/submissions/CIK0000320193.json"
    status, body = fetch(url, {"User-Agent": agent})
    return "ok" if status == 200 and json.loads(body).get("cik") else f"http {status}"


def check_fred() -> str:
    query = urllib.parse.urlencode(
        {
            "series_id": "DGS10",
            "api_key": os.environ["FRED_API_KEY"],
            "file_type": "json",
            "limit": 1,
        }
    )
    status, body = fetch(f"https://api.stlouisfed.org/fred/series/observations?{query}")
    return "ok" if status == 200 and "observations" in json.loads(body) else f"http {status}"


def main() -> None:
    checks = {
        "database": check_database,
        "tiingo": check_tiingo,
        "tiingo_delisted": check_tiingo_delisted,
        "sec": check_sec,
        "fred": check_fred,
    }
    failed = False
    for name, check in checks.items():
        try:
            result = check()
        except Exception as exc:  # Class name only, as messages can contain URLs with keys.
            result = f"failed: {type(exc).__name__}"
        print(f"{name}: {result}")
        if name != "tiingo_delisted" and result != "ok":
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
