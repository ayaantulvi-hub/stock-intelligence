"""US election dates, fixed by law as the Tuesday after the first Monday of November."""

from datetime import date, timedelta

WINDOW = 60


def election_day(year: int) -> date:
    first = date(year, 11, 1)
    monday = first + timedelta(days=(7 - first.weekday()) % 7)
    return monday + timedelta(days=1)


def next_election(today: date) -> tuple[date, str]:
    """The next federal election, and whether it is presidential or midterm."""
    year = today.year if today.year % 2 == 0 else today.year + 1
    if election_day(year) < today:
        year += 2
    return election_day(year), "presidential" if year % 4 == 0 else "midterm"


def is_midterm_year(day: date) -> bool:
    return day.year % 4 == 2


def election_window(day: date) -> int:
    """-1 in the 60 days before a federal election, 1 in the 60 after, otherwise 0."""
    for year in (day.year - 1, day.year):
        if year % 2 == 0:
            gap = (day - election_day(year)).days
            if 0 <= gap <= WINDOW:
                return 1
    if day.year % 2 == 0:
        gap = (election_day(day.year) - day).days
        if 0 < gap <= WINDOW:
            return -1
    return 0
