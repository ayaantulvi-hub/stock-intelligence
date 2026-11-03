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


def describe_database_url() -> str:
    """Describe the address's shape without printing any of it."""
    value = os.environ.get("DATABASE_URL", "")
    return (
        f"length {len(value)}, "
        f"starts_with_postgres {value.startswith(('postgresql://', 'postgres://'))}, "
        f"has_space {' ' in value.strip()}, "
        f"outer_whitespace {value != value.strip()}, "
        f"has_quote {chr(39) in value or chr(34) in value}, "
        f"at_signs {value.count('@')}"
    )


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


def check_adjustment() -> None:
    """Compare adjusted closes with Tiingo's own, which is the independent reference."""
    from datetime import date

    import pandas as pd
    from sqlalchemy import text as sql

    from stockintel.charts import adjust

    headers = {"Authorization": f"Token {os.environ['TIINGO_API_TOKEN']}"}
    engine = create_engine(Settings().database_url)
    for ticker in ("AAPL", "NVDA", "JPM", "WMT", "XOM"):
        with engine.connect() as conn:
            rows = conn.execute(
                sql(
                    """SELECT DISTINCT ON (market_date) market_date, open, high, low, close,
                         volume, div_cash, split_factor
                       FROM price_bars p JOIN securities s ON s.id = p.security_id
                       WHERE s.ticker = :ticker ORDER BY market_date, p.id DESC"""
                ),
                {"ticker": ticker},
            ).all()
        if not rows:
            print(f"adjustment {ticker}: no stored bars")
            continue
        first, last = rows[0].market_date, rows[-1].market_date
        url = (
            f"https://api.tiingo.com/tiingo/daily/{ticker.lower()}/prices"
            f"?startDate={first}&endDate={last}"
        )
        status, body = fetch(url, headers)
        if status != 200:
            print(f"adjustment {ticker}: http {status}")
            continue
        reference = {date.fromisoformat(r["date"][:10]): r["adjClose"] for r in json.loads(body)}
        ours = adjust(pd.DataFrame([row._mapping for row in rows]))
        errors = [
            abs(close / reference[day] - 1)
            for day, close in zip(ours["market_date"], ours["close"], strict=True)
            if day in reference
        ]
        print(
            f"adjustment {ticker}: bars {len(errors)}, "
            f"worst {max(errors):.4%}, average {sum(errors) / len(errors):.4%}"
        )


def probe_sec_shapes() -> None:
    """Print field names of SEC company facts and a Form 4, needed to design the connectors."""
    agent = f"stock-intelligence {os.environ['SEC_CONTACT_EMAIL']}"
    status, body = fetch(
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json", {"User-Agent": agent}
    )
    print("facts status", status, "bytes", len(body))
    data = json.loads(body)
    print("taxonomies", {key: len(value) for key, value in data["facts"].items()})
    print("dei", sorted(data["facts"]["dei"]))
    for tag in (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "NetIncomeLoss",
        "Assets",
        "StockholdersEquity",
        "NetCashProvidedByUsedInOperatingActivities",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "LongTermDebtNoncurrent",
        "GrossProfit",
        "CashAndCashEquivalentsAtCarryingValue",
    ):
        concept = data["facts"]["us-gaap"].get(tag)
        if concept:
            units = concept["units"]
            first = next(iter(units.values()))
            print(tag, list(units), len(first), first[-1])
        else:
            print(tag, "absent")
    status, body = fetch(
        "https://data.sec.gov/submissions/CIK0000320193.json", {"User-Agent": agent}
    )
    recent = json.loads(body)["filings"]["recent"]
    index = recent["form"].index("4")
    accession, document = recent["accessionNumber"][index], recent["primaryDocument"][index]
    print("form4 document", document)
    bare = document.rsplit("/", 1)[-1]
    url = f"https://www.sec.gov/Archives/edgar/data/320193/{accession.replace('-', '')}/{bare}"
    status, body = fetch(url, {"User-Agent": agent})
    print("form4 status", status)
    print(body[:2500].decode("utf8", "replace"))


def main() -> None:
    probe_sec_shapes()
    checks = {
        "database": check_database,
        "tiingo": check_tiingo,
        "tiingo_delisted": check_tiingo_delisted,
        "sec": check_sec,
        "fred": check_fred,
    }
    failed = False
    print(f"database address: {describe_database_url()}")
    for name, check in checks.items():
        try:
            result = check()
        # Class name only, as messages can contain URLs with keys.
        except Exception as exc:  # noqa: BLE001
            result = f"failed: {type(exc).__name__}"
        print(f"{name}: {result}")
        if name != "tiingo_delisted" and result != "ok":
            failed = True
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
