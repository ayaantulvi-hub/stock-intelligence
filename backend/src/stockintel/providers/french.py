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

DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
SOURCE = "Kenneth R. French Data Library"
MIN_ROWS = 20_000  # About 100 years of trading days; fewer means a broken or partial file.
ROW = re.compile(r"^\s*(\d{8})\s*,(.*)$")


def parse_daily(content: bytes) -> list[tuple[date, float, float]]:
    """(day, market excess return, risk-free return) from the zipped CSV, as decimals."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            text = archive.read(archive.namelist()[0]).decode("latin-1")
    except (zipfile.BadZipFile, IndexError, KeyError):
        raise FeedError("French library: the download is not a readable zip file") from None
    header, rows = None, []
    for line in text.splitlines():
        if header is None and "Mkt-RF" in line:
            header = [c.strip() for c in line.split(",")]
            continue
        match = ROW.match(line)
        if header is None or not match:
            continue
        values = dict(zip(header[1:], [v.strip() for v in match.group(2).split(",")], strict=False))
        try:
            day = datetime.strptime(match.group(1), "%Y%m%d").date()
            rows.append((day, float(values["Mkt-RF"]) / 100, float(values["RF"]) / 100))
        except (KeyError, ValueError):
            raise FeedError(f"French library: unreadable row for {match.group(1)}") from None
    if header is None:
        raise FeedError("French library: no Mkt-RF column found")
    days = [r[0] for r in rows]
    if len(rows) < MIN_ROWS:
        raise FeedError(f"French library: only {len(rows)} daily rows, expected {MIN_ROWS}+")
    if any(b <= a for a, b in itertools.pairwise(days)):
        raise FeedError("French library: dates are not in order")
    return rows


class FrenchProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=60, follow_redirects=True)

    def daily_market(self) -> tuple[list[tuple[date, float, float]], Provenance]:
        try:
            response = self.client.get(DAILY_URL)
        except httpx.HTTPError as exc:
            raise FeedError(f"French library: {type(exc).__name__}") from None
        if response.status_code != 200:
            raise FeedError(f"French library: HTTP {response.status_code}")
        rows = parse_daily(response.content)
        return rows, Provenance(SOURCE, DAILY_URL, datetime.now(UTC), "end_of_day")
