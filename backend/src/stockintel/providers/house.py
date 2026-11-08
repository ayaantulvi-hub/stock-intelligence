"""House of Representatives stock trade reports (Periodic Transaction Reports, PTRs).

Members must report trades by themselves, a spouse or a dependent child within 45 days under
the STOCK Act. The House Clerk posts a yearly index and each report as a PDF:
  https://disclosures-clerk.house.gov/public_disc/financial-pdfs/<YEAR>FD.zip
  https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/<YEAR>/<DocID>.pdf
The text reading follows trader-pelosi's ptr.py from github.com/Jakeschincariol/day-trader-skill
(MIT licence). Reports arrive days or weeks after a trade, and amounts are ranges.
The Senate is not covered: its reports sit behind an agreement page.
"""

import io
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from stockintel.providers.base import FeedError, Provenance

INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"
ACTIONS = {"P": "Buy", "S": "Sell", "S (partial)": "Partial sale", "E": "Exchange"}
OWNERS = {"SP": "Spouse", "JT": "Joint", "DC": "Dependent child", "": "Member"}

TXN = re.compile(
    r"^\s*(?:(?P<owner>SP|JT|DC)\s+)?(?P<asset>.*?)\s+(?P<type>S \(partial\)|P|S|E)\s+"
    r"(?P<date>\d{2}/\d{2}/\d{4})\s+(?P<notified>\d{2}/\d{2}/\d{4})\s+(?P<amount>\S.*?)\s*$"
)
LABEL = re.compile(
    r"^\s*(F(?:ILING)?\s+S(?:TATUS)?|D(?:ESCRIPTION)?|S(?:UBHOLDING)?\s+O(?:F)?|L(?:OCATION)?)"
    r"\s*:\s*(.*)$",
    re.IGNORECASE,
)
PAGE_HEADER = re.compile(
    r"^\s*(ID\s+Owner\s+Asset|Type\s+Date\b|Type$|Date$|Gains >$|\$200\?$)", re.IGNORECASE
)
END = re.compile(r"^\s*(\* For the complete|I CERTIFY|Digitally Signed|Filing ID #)", re.IGNORECASE)


@dataclass(frozen=True)
class Report:
    doc_id: str
    member: str
    filed: date | None
    year: int
    url: str


def mdy(text: str) -> date | None:
    match = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*$", text or "")
    if not match:
        return None
    month, day, year = (int(x) for x in match.groups())
    try:
        return date(year + 2000 if year < 100 else year, month, day)
    except ValueError:
        return None


def parse_index(data: bytes, year: int) -> list[Report]:
    """Trade reports (FilingType P) from a yearly index, as a ZIP or its XML."""
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise FeedError("House Clerk: no XML inside the index ZIP")
            data = archive.read(names[0])
    try:
        root = ET.fromstring(data)
    except ET.ParseError:
        raise FeedError("House Clerk: the index is not valid XML") from None
    reports = []
    for member in root.iter("Member"):
        fields = {child.tag: (child.text or "").strip() for child in member}
        if fields.get("FilingType") != "P" or not fields.get("DocID"):
            continue
        name = " ".join(
            x for x in (fields.get("First"), fields.get("Last"), fields.get("Suffix")) if x
        )
        filed_year = int(fields.get("Year") or year)
        reports.append(
            Report(
                doc_id=fields["DocID"],
                member=name,
                filed=mdy(fields.get("FilingDate", "")),
                year=filed_year,
                url=PTR_URL.format(year=filed_year, doc=fields["DocID"]),
            )
        )
    return reports


def parse_report(text: str, filed: date | None) -> list[dict]:
    """Trade lines from `pdftotext -layout` text of one report."""
    rows: list[dict] = []
    current = None
    mode = None
    amount_open = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        found = TXN.match(line)
        if found and mdy(found.group("date")):
            if current:
                rows.append(current)
            current = {
                "owner": OWNERS.get(found.group("owner") or "", "Member"),
                "asset": found.group("asset"),
                "action": ACTIONS.get(found.group("type"), found.group("type")),
                "trade_date": mdy(found.group("date")),
                "amount": found.group("amount"),
            }
            amount_open = current["amount"].endswith("-")
            mode = "asset"
            continue
        if current is None:
            continue
        if not stripped:
            if mode == "asset" and "[" in current["asset"]:
                mode = "labels"
            continue
        if PAGE_HEADER.match(stripped):
            continue
        if END.match(stripped) or LABEL.match(line):
            mode = "labels"
            continue
        if mode == "asset":
            parts = re.split(r"\s{2,}", stripped)
            if amount_open and re.fullmatch(r"\$[\d,]+", parts[-1]):
                current["amount"] += " " + parts.pop()
                amount_open = False
            if parts and parts[0]:
                current["asset"] += " " + " ".join(parts)
    if current:
        rows.append(current)
    for row in rows:
        asset = " ".join(row["asset"].split())
        tickers = re.findall(r"\(([A-Z][A-Z0-9.\-/]{0,9})\)", asset)
        kind = re.findall(r"\[([A-Z]{2})\]", asset)
        row["ticker"] = tickers[-1].replace(".", "-").replace("/", "-") if tickers else None
        # [ST] is a stock, [OP] an option. Options are kept but marked in the asset name.
        row["asset"] = asset
        row["kind"] = kind[-1] if kind else None
        row["amount"] = " ".join(row["amount"].split())
        row["days_to_file"] = (
            (filed - row["trade_date"]).days if filed and row["trade_date"] else None
        )
    return rows


class HouseProvider:
    def __init__(self, client: httpx.Client | None = None):
        self.client = client or httpx.Client(timeout=60, follow_redirects=True)
        self.pdftotext = shutil.which("pdftotext")

    def _get(self, url: str) -> bytes:
        try:
            response = self.client.get(url)
        except httpx.HTTPError as exc:
            raise FeedError(f"House Clerk: request failed ({type(exc).__name__})") from None
        if response.status_code != 200:
            raise FeedError(f"House Clerk: HTTP {response.status_code}")
        return response.content

    def reports(self, year: int) -> tuple[list[Report], Provenance]:
        url = INDEX_URL.format(year=year)
        return parse_index(self._get(url), year), Provenance(
            "House Clerk", url, datetime.now(UTC), "end_of_day"
        )

    def trades(self, report: Report) -> list[dict]:
        if not self.pdftotext:
            raise FeedError("House Clerk: pdftotext is not installed, so reports can't be read")
        pdf = self._get(report.url)
        with tempfile.NamedTemporaryFile(suffix=".pdf") as handle:
            handle.write(pdf)
            handle.flush()
            done = subprocess.run(
                [self.pdftotext, "-layout", handle.name, "-"],
                check=False,
                capture_output=True,
                timeout=60,
            )
        if done.returncode != 0:
            raise FeedError("House Clerk: the report PDF couldn't be read")
        return parse_report(done.stdout.decode("utf-8", "replace"), report.filed)
