"""Provider interfaces and the records they return."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


class FeedError(Exception):
    """A source failed or returned something unusable. Nothing from it is stored."""


class NotAvailable(FeedError):
    """The source has no such record. Normal for some companies, and not an outage."""


class RateLimited(FeedError):
    """The source refused because a request limit was reached."""


@dataclass(frozen=True)
class Provenance:
    source_name: str
    source_url: str  # Must never contain an API key.
    retrieved_at: datetime
    data_status: str


@dataclass(frozen=True)
class PriceBar:
    market_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    div_cash: float
    split_factor: float


@dataclass(frozen=True)
class Filing:
    accession_number: str
    form: str
    filing_date: date
    report_date: date | None
    accepted_at: datetime | None
    document_url: str
    items: str | None = None


@dataclass(frozen=True)
class Observation:
    observation_date: date
    realtime_start: date
    value: float | None  # None means the source published no value.


@dataclass(frozen=True)
class Fact:
    tag: str
    unit: str
    period_start: date | None
    period_end: date
    value: float
    accession_number: str
    fiscal_period: str | None
    form: str
    filed: date
    document_url: str


@dataclass(frozen=True)
class InsiderDocument:
    accession_number: str
    filed: date
    url: str


@dataclass(frozen=True)
class InsiderTrade:
    line: int
    owner: str
    title: str | None
    transaction_date: date
    code: str
    shares: float
    price: float | None
    planned_sale: bool


@dataclass(frozen=True)
class Listing:
    ticker: str
    cik: int
    name: str
    exchange: str


class PriceProvider(Protocol):
    def daily_bars(
        self, ticker: str, start: date, end: date
    ) -> tuple[list[PriceBar], Provenance]: ...


class FilingsProvider(Protocol):
    def listings(self) -> tuple[list[Listing], Provenance]: ...

    def filings(self, cik: int) -> tuple[list[Filing], Provenance]: ...


class EconomicProvider(Protocol):
    def observations(self, series_id: str, start: date) -> tuple[list[Observation], Provenance]: ...
