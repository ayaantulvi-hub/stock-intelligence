"""News feed. Every response here is a TEST FIXTURE."""

from datetime import UTC, date, datetime

import httpx
import pytest
from sqlalchemy import text

from stockintel import context
from stockintel.ingest import run_news
from stockintel.providers.base import FeedError, RateLimited
from stockintel.providers.gdelt import GdeltProvider, company_query, full_query

ARTICLE = {
    "url": "https://www.reuters.com/fixture",
    "title": "Fixture headline",
    "domain": "reuters.com",
    "seendate": "20261105T100000Z",
}
TONE = {
    "timeline": [
        {
            "data": [
                {"date": "20261104T000000Z", "value": -2.0},
                {"date": "20261104T120000Z", "value": -4.0},
                {"date": "20261105T000000Z", "value": 1.0},
            ]
        }
    ]
}


def provider(handler):
    return GdeltProvider(httpx.Client(transport=httpx.MockTransport(handler)), wait=0)


def good(request):
    if request.url.params["mode"] == "TimelineTone":
        return httpx.Response(200, json=TONE)
    return httpx.Response(200, json={"articles": [ARTICLE]})


def test_company_names_become_everyday_searches():
    assert company_query("LAM RESEARCH CORP").startswith('"Lam Research"')
    assert company_query("Palantir Technologies Inc.").startswith('"Palantir"')
    assert company_query("Applied Materials, Inc. /DE").startswith('"Applied Materials"')


def test_only_established_outlets_are_searched():
    query = full_query("x")
    assert "domainis:ft.com" in query and "domainis:reuters.com" in query
    assert "twitter" not in query and "reddit" not in query


def test_articles_and_daily_tone():
    source = provider(good)
    found, provenance = source.articles("x")
    assert found[0].domain == "reuters.com" and provenance.source_name == "GDELT"
    tones, _ = source.tone("x")
    assert tones == {date(2026, 11, 4): -3.0, date(2026, 11, 5): 1.0}


def test_empty_results_are_empty_not_an_error():
    source = provider(lambda request: httpx.Response(200, text=""))
    assert source.articles("x")[0] == []


def test_bad_replies_are_reported():
    with pytest.raises(FeedError):
        provider(lambda request: httpx.Response(200, text="Query too short")).articles("x")
    with pytest.raises(RateLimited):
        provider(lambda request: httpx.Response(429)).articles("x")


def test_news_is_stored_once_and_shown_with_its_source(engine):
    subjects = {"Inflation": "x"}
    assert run_news(engine, provider(good), subjects) == "ok"
    assert run_news(engine, provider(good), subjects) == "ok"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM news_articles")).scalar() == 1
    result = context.headlines(engine, "Inflation", datetime(2026, 11, 6, tzinfo=UTC).date())
    assert result["articles"][0]["domain"] == "reuters.com"
    assert result["tone"] == "Not verified"


def test_tone_words():
    assert context.tone_word(-4.0, -1.0) == "More negative than usual"
    assert context.tone_word(1.0, -1.0) == "More positive than usual"
    assert context.tone_word(-1.2, -1.0) == "About usual"
    assert context.tone_word(None, None) == "Not verified"
