"""Elections, policy data and the big picture. TEST FIXTURE values only."""

from datetime import UTC, date, datetime

import httpx
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import text

from stockintel import calendar_events, context, forecast
from stockintel.ingest import run_policy
from stockintel.providers.base import FeedError
from stockintel.providers.federal_register import FederalRegisterProvider, topic_of


def test_election_days_match_the_rule():
    assert calendar_events.election_day(2026) == date(2026, 11, 3)
    assert calendar_events.election_day(2024) == date(2024, 11, 5)
    assert calendar_events.election_day(2028) == date(2028, 11, 7)


def test_election_windows_use_only_the_calendar():
    assert calendar_events.election_window(date(2026, 10, 1)) == -1
    assert calendar_events.election_window(date(2026, 11, 5)) == 1
    assert calendar_events.election_window(date(2027, 1, 1)) == 1
    assert calendar_events.election_window(date(2026, 6, 1)) == 0
    assert calendar_events.election_window(date(2027, 6, 1)) == 0


def test_next_election_after_a_midterm_is_presidential():
    assert calendar_events.next_election(date(2026, 11, 5)) == (date(2028, 11, 7), "presidential")
    assert calendar_events.next_election(date(2026, 11, 1)) == (date(2026, 11, 3), "midterm")


def test_only_policy_titles_get_topics():
    assert topic_of("Adjusting Imports of Steel Into the United States") == "Trade and tariffs"
    assert topic_of("National Farmers Day, 2026") is None


def test_inverted_curve_warns_but_is_not_a_sell_signal():
    result = context.curve(4.0, 4.5, -0.2, date(2026, 11, 1))
    assert result["state"] == context.BAD
    assert "not a sell signal" in result["meaning"]
    assert context.curve(4.5, 4.0, 0.5, date(2026, 11, 1))["state"] == context.GOOD
    assert context.curve(None, 4.0, None, None)["reading"] == "Not verified"


def test_rate_direction_and_uncertainty():
    assert context.rates(3.5, 4.0, date(2026, 11, 1))["state"] == context.GOOD
    assert context.rates(4.5, 4.0, date(2026, 11, 1))["state"] == context.BAD
    assert context.uncertainty(300.0, 100.0, date(2026, 11, 1))["state"] == context.BAD
    assert context.uncertainty(None, None, None)["state"] == context.UNKNOWN


def test_big_picture_says_not_verified_with_no_data(engine):
    result = context.build(engine, date(2026, 11, 5))
    assert result["actions"] == []
    assert result["cards"][0]["reading"] == "Not verified"
    assert result["cards"][3]["title"] == "US dollar"
    assert result["cards"][3]["reading"] == "Not verified"
    assert result["cards"][4]["title"] == "US elections"


def test_dollar_card_reads_the_month():
    assert context.dollar(124.0, 120.0, date(2026, 11, 1))["state"] == context.BAD
    assert context.dollar(118.0, 121.0, date(2026, 11, 1))["state"] == context.GOOD
    assert context.dollar(120.5, 120.0, date(2026, 11, 1))["state"] == context.NEUTRAL


def responses(results, total_pages=1):
    def handler(request):
        return httpx.Response(200, json={"results": results, "total_pages": total_pages})

    return httpx.Client(transport=httpx.MockTransport(handler))


ROW = {
    "document_number": "2026-1",
    "title": "Adjusting Imports of Steel",
    "publication_date": "2026-03-02",
    "html_url": "https://www.federalregister.gov/d/2026-1",
    "subtype": "Proclamation",
}


def test_provider_keeps_orders_and_proclamations_only():
    other = {**ROW, "document_number": "2026-2", "subtype": "Memorandum"}
    found, provenance = FederalRegisterProvider(responses([ROW, other])).documents(
        date(2026, 1, 1), date(2026, 12, 31)
    )
    assert [item.document_number for item in found] == ["2026-1"]
    assert found[0].topic == "Trade and tariffs"
    assert provenance.source_name == "Federal Register"


def test_provider_reports_a_bad_shape():
    with pytest.raises(FeedError):
        FederalRegisterProvider(responses([{"title": "x", "subtype": "Proclamation"}])).documents(
            date(2026, 1, 1), date(2026, 1, 2)
        )


def test_policy_documents_store_once_with_provenance(engine):
    provider = FederalRegisterProvider(responses([ROW]))
    now = datetime(2026, 3, 5, tzinfo=UTC)
    assert run_policy(engine, provider, now) in ("ok", "partial")
    assert run_policy(engine, provider, now) in ("ok", "partial")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM policy_documents")).scalar() == 1
        source = conn.execute(
            text(
                """SELECT d.name FROM policy_documents p JOIN fetches f ON f.id = p.fetch_id
                   JOIN data_sources d ON d.id = f.source_id"""
            )
        ).scalar()
    assert source == "Federal Register"


def test_sensitivity_finds_the_link_and_uses_only_earlier_days():
    days = pd.date_range("2024-01-01", periods=400, freq="B")
    driver = pd.Series(np.random.default_rng(3).normal(0, 0.05, 400), index=days)
    moves = pd.Series(2 * driver.to_numpy())
    result = forecast.sensitivity(moves, pd.Series(days), driver)
    assert np.isnan(result[100])
    assert result[-1] == pytest.approx(2.0)
    changed = moves.copy()
    changed.iloc[-1] = 9.0
    assert forecast.sensitivity(changed, pd.Series(days), driver)[-1] == result[-1]


def test_no_driver_stays_missing():
    assert np.isnan(
        forecast.sensitivity(
            pd.Series([0.1] * 5), pd.Series(pd.date_range("2024-01-01", periods=5)), None
        )
    ).all()
