"""When the next decisions are due."""

from datetime import UTC, datetime

from stockintel.market import next_decision


def at(*parts):
    return datetime(*parts, tzinfo=UTC)


def test_later_today_when_the_run_is_still_to_come():
    assert next_decision(at(2026, 11, 5, 8, 0)) == at(2026, 11, 5, 10, 50)


def test_tomorrow_once_today_has_passed():
    assert next_decision(at(2026, 11, 5, 11, 0)) == at(2026, 11, 6, 10, 50)


def test_friday_evening_goes_to_saturday_and_saturday_evening_to_tuesday():
    assert next_decision(at(2026, 11, 6, 20, 0)) == at(2026, 11, 7, 10, 50)
    assert next_decision(at(2026, 11, 7, 20, 0)) == at(2026, 11, 10, 10, 50)
