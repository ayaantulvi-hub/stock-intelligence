"""Automatic data checks. They report problems and never repair the data."""

import itertools
from dataclasses import dataclass
from datetime import date

from stockintel.market import sessions_between
from stockintel.providers.base import PriceBar

OUTLIER_MOVE = 0.5


@dataclass(frozen=True)
class Issue:
    kind: str
    market_date: date | None
    detail: str


def bar_problem(bar: PriceBar) -> str | None:
    """Why a bar is impossible, or None. Impossible bars are not stored."""
    if min(bar.open, bar.high, bar.low, bar.close) <= 0:
        return "non-positive price"
    if bar.high < max(bar.open, bar.close, bar.low) or bar.low > min(bar.open, bar.close):
        return "high or low does not contain the day's prices"
    if bar.volume < 0:
        return "negative volume"
    if bar.split_factor <= 0 or bar.div_cash < 0:
        return "invalid split or dividend"
    return None


def find_issues(bars: list[PriceBar]) -> list[Issue]:
    """Check stored-quality bars for suspicious moves and missing sessions."""
    if not bars:
        return []
    bars = sorted(bars, key=lambda bar: bar.market_date)
    issues = []
    for previous, bar in itertools.pairwise(bars):
        move = bar.close / previous.close - 1
        if abs(move) > OUTLIER_MOVE and bar.split_factor == 1:
            issues.append(
                Issue("outlier", bar.market_date, f"close moved {move:+.0%} with no split")
            )
    present = {bar.market_date for bar in bars}
    for session in sessions_between(bars[0].market_date, bars[-1].market_date):
        if session not in present:
            issues.append(Issue("gap", session, "no bar for a trading session"))
    return issues
