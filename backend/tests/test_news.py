"""News feeds. Every response here is a TEST FIXTURE."""

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy import text

from stockintel import context
from stockintel.ingest import run_news
from stockintel.providers import news
from stockintel.providers.base import FeedError

XML = """<rss><channel>
<item><title>Lam Research shares jump as inflation cools</title>
<link>https://www.bbc.co.uk/news/fixture</link>
<pubDate>Thu, 05 Nov 2026 10:00:00 GMT</pubDate></item>
<item><title>No date here</title><link>https://www.bbc.co.uk/x</link></item>
</channel></rss>"""
NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def provider(handler):
    return news.NewsProvider(httpx.Client(transport=httpx.MockTransport(handler)))


def good(request):
    return httpx.Response(200, text=XML)


def test_company_names_become_everyday_names():
    assert news.plain_name("LAM RESEARCH CORP") == "Lam Research"
    assert news.plain_name("Palantir Technologies Inc.") == "Palantir"
    assert news.plain_name("Applied Materials, Inc. /DE") == "Applied Materials"


def test_common_word_names_need_business_context():
    assert news.matches_company("Lam Research", "Lam Research beats forecasts")
    assert not news.matches_company("Target", "Fed misses Target on inflation")
    assert news.matches_company("Target", "Target shares fall")


def test_topics_and_mood():
    assert "Inflation" in news.topics_of("Inflation cools in October")
    assert news.headline_mood("Shares surge to a record") == 2
    assert news.headline_mood("Profit warning as sales fall") < 1


def test_stories_reach_the_right_level():
    assert "Tariffs and trade" in news.topics_of("Trump raises steel tariffs")
    assert "Industry: Metals and mining" in news.industries_of("Trump raises steel tariffs")
    assert news.industry_of(3674) == "Industry: Chips"
    assert news.industry_of(6021) == "Industry: Banks and finance"
    assert news.industry_of(None) is None


def test_parse_skips_items_with_no_date_and_rejects_bad_xml():
    found = news.parse_feed(XML, "BBC")
    assert [item.title for item in found] == ["Lam Research shares jump as inflation cools"]
    with pytest.raises(FeedError):
        news.parse_feed("not xml", "BBC")


def test_one_failed_feed_doesnt_stop_the_rest(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('LRCX', 1, 'LAM RESEARCH CORP', 'NASDAQ', 1)"""
            )
        )

    def mixed(request):
        return httpx.Response(500) if "bbc" in str(request.url) else httpx.Response(200, text=XML)

    assert run_news(engine, provider(mixed), NOW) == "partial"
    assert run_news(engine, provider(mixed), NOW) == "partial"
    stock = context.headlines(engine, "LRCX", NOW.date())
    assert len(stock["articles"]) == 1
    assert context.headlines(engine, "Inflation", NOW.date())["articles"]
    grouped = context.news(engine, NOW.date())
    assert grouped["companies"][0]["subject"] == "LRCX"
    assert grouped["market"][0]["subject"] == "Inflation"
    assert context.stock_news(engine, "LRCX", NOW.date())["articles"]


def test_tone_words():
    assert context.tone_word(-1.0, 0.0) == "More negative than usual"
    assert context.tone_word(1.0, 0.0) == "More positive than usual"
    assert context.tone_word(0.1, 0.0) == "About usual"
    assert context.tone_word(None, None) == "Not verified"
