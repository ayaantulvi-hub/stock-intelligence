"""US market calendar: holidays, early closes and when daily prices should exist."""

from datetime import UTC, date, datetime, timedelta

import exchange_calendars as xcals
import pandas as pd

# Tiingo publishes most US prices by 5:30pm ET. Allow a margin after the close.
PUBLISH_DELAY = timedelta(hours=3)
_calendar = None


def calendar():
    global _calendar
    if _calendar is None:
        _calendar = xcals.get_calendar("XNYS")
    return _calendar


def session_close(day: date) -> datetime:
    """The session's real closing time, which covers early closes. Raises for non-sessions."""
    return calendar().session_close(pd.Timestamp(day)).to_pydatetime().astimezone(UTC)


def is_session(day: date) -> bool:
    return bool(calendar().is_session(pd.Timestamp(day)))


def sessions_between(start: date, end: date) -> list[date]:
    return [
        ts.date() for ts in calendar().sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    ]


def latest_expected_session(now: datetime) -> date:
    """The newest session whose daily prices should be published by now."""
    day = now.astimezone(UTC).date() + timedelta(days=1)
    for _ in range(15):
        if is_session(day) and session_close(day) + PUBLISH_DELAY <= now:
            return day
        day -= timedelta(days=1)
    raise RuntimeError("no recent trading session found")


def is_stale(latest_bar: date | None, now: datetime) -> bool:
    return latest_bar is None or latest_bar < latest_expected_session(now)
