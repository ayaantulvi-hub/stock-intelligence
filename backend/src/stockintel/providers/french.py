"""Kenneth R. French Data Library: daily Fama/French factors since July 1926.
Page: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html

Used: Mkt-RF (the value-weighted return of all US firms on the NYSE, AMEX and NASDAQ, minus
the one-month Treasury bill rate) and RF (that bill rate). The file gives percent; values are
stored as decimals. The library shows a copyright notice and no licence, so the data stays in
the private database and only summary results are published.
"""

import io
import itertools
import re
import zipfile
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance

BASE = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
DAILY_URL = BASE + "F-F_Research_Data_Factors_daily_CSV.zip"
SOURCE = "Kenneth R. French Data Library"
MIN_ROWS = 20_000  # About 100 years of trading days; fewer means a broken or partial file.
ROW = re.compile(r"^\s*(\d{8})\s*,(.*)$")

# Daily files and the columns kept from each, as stored series names. Every non-momentum
# factor in the library, US and developed markets outside the US. Short-term reversal is left
# out because it turns over its whole portfolio monthly and these returns exclude trading costs.
# Fixed before any factor-momentum result was seen.
FILES = {
    "market": (DAILY_URL, {"Mkt-RF": "mkt_rf", "RF": "rf"}, MIN_ROWS),
    "us five factors": (
        BASE + "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
        {"SMB": "us_smb", "HML": "us_hml", "RMW": "us_rmw", "CMA": "us_cma"},
        10_000,
    ),
    "us long-term reversal": (
        BASE + "F-F_LT_Reversal_Factor_daily_CSV.zip",
        {"LT_Rev": "us_lt_rev"},
        20_000,
    ),
    "developed ex US": (
        BASE + "Developed_ex_US_5_Factors_Daily_CSV.zip",
        {
            "Mkt-RF": "devx_mkt_rf",
            "SMB": "devx_smb",
            "HML": "devx_hml",
            "RMW": "devx_rmw",
            "CMA": "devx_cma",
        },
        5_000,
    ),
}


def _text(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return archive.read(archive.namelist()[0]).decode("latin-1")
    except (zipfile.BadZipFile, IndexError, KeyError):
        raise FeedError("French library: the download is not a readable zip file") from None


def parse_columns(
    content: bytes, columns: dict[str, str], min_rows: int
) -> list[tuple[date, dict[str, float]]]:
    """Rows of (day, {series: decimal return}) for the wanted columns of a zipped daily CSV.
    The header is the first line that starts with a comma and names a wanted column."""
    header, rows = None, []
    for line in _text(content).splitlines():
        cells = [c.strip() for c in line.split(",")]
        if header is None and line.lstrip().startswith(",") and set(columns) & set(cells):
            missing = set(columns) - set(cells)
            if missing:
                raise FeedError(f"French library: no {', '.join(sorted(missing))} column found")
            header = cells
            continue
        match = ROW.match(line)
        if header is None or not match:
            continue
        values = dict(zip(header[1:], [v.strip() for v in match.group(2).split(",")], strict=False))
        try:
            day = datetime.strptime(match.group(1), "%Y%m%d").date()
            rows.append((day, {name: float(values[col]) / 100 for col, name in columns.items()}))
        except (KeyError, ValueError):
            raise FeedError(f"French library: unreadable row for {match.group(1)}") from None
    if header is None:
        raise FeedError(f"French library: no {', '.join(sorted(columns))} column found")
    if len(rows) < min_rows:
        raise FeedError(f"French library: only {len(rows)} daily rows, expected {min_rows}+")
    days = [r[0] for r in rows]
    if any(b <= a for a, b in itertools.pairwise(days)):
        raise FeedError("French library: dates are not in order")
    return rows


def parse_daily(content: bytes) -> list[tuple[date, float, float]]:
    """(day, market excess return, risk-free return) from the market file, as decimals."""
    rows = parse_columns(content, FILES["market"][1], MIN_ROWS)
    return [(day, v["mkt_rf"], v["rf"]) for day, v in rows]


class FrenchProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=60, follow_redirects=True)

    def daily(self, name: str) -> tuple[list[tuple[date, dict[str, float]]], Provenance]:
        url, columns, min_rows = FILES[name]
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise FeedError(f"French library: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise FeedError(f"French library: HTTP {response.status_code}")
        rows = parse_columns(response.content, columns, min_rows)
        return rows, Provenance(SOURCE, url, datetime.now(UTC), "end_of_day")
