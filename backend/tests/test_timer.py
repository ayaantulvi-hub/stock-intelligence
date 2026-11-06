"""When the next decisions are due."""

from datetime import UTC, datetime

from sqlalchemy import text

from stockintel.forecast import decisions_due
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


def test_a_missed_run_is_picked_up_until_the_market_opens(engine):
    friday_late = datetime(2026, 11, 6, 11, 20, tzinfo=UTC)
    assert decisions_due(engine, datetime(2026, 11, 6, 10, 20, tzinfo=UTC)) is False
    assert decisions_due(engine, friday_late) is True
    assert decisions_due(engine, datetime(2026, 11, 6, 15, 0, tzinfo=UTC)) is False


def test_decisions_are_not_due_twice(engine):
    with engine.begin() as conn:
        security = conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('DUE', '1', 'Due', 'NYSE', 1) RETURNING id"""
            )
        ).scalar()
        conn.execute(
            text(
                """INSERT INTO forecasts (created_at, security_id, as_of_session, target_session,
                     target_close, last_close, p_up, p_flat, p_down, range_low, range_high,
                     next_day_edge, rank_edge, confidence, drivers)
                   VALUES ('2026-11-06 11:00+00', :id, '2026-11-05', '2026-11-06',
                     '2026-11-06 21:00+00', 1, .4, .2, .4, 1, 2, false, false, 'Low', '[]')"""
            ),
            {"id": security},
        )
    assert decisions_due(engine, datetime(2026, 11, 6, 11, 20, tzinfo=UTC)) is False
