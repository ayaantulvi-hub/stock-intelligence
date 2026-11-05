"""Bad news in decisions. TEST FIXTURE headlines only."""

from datetime import UTC, datetime

from sqlalchemy import text

from stockintel import advice, news_watch, queries

NOW = datetime(2026, 11, 5, 12, tzinfo=UTC)


def row(title, domain):
    return {"title": title, "domain": domain, "url": f"https://{domain}/x", "seen_at": NOW}


BAD = [
    row("Chip stocks plunge", "BBC"),
    row("Chipmakers tumble on fears", "CNBC"),
    row("Chips slump again", "FT"),
]


def test_several_outlets_must_agree():
    assert news_watch.assess(BAD)["bad"] == 3
    assert news_watch.assess(BAD[:2]) is None
    assert news_watch.assess([{**item, "domain": "BBC"} for item in BAD]) is None


def test_good_news_cancels_a_warning():
    good = [row("Chips surge to a record", "BBC")] * 2
    assert news_watch.assess(BAD + good) is None


def answer(call, owned=False):
    return {"call": call, "reason": "r", "proven": True, "kind": "buy", "owned": owned}


def test_bad_news_stops_a_buy_and_never_creates_one():
    result = advice.apply_news(answer("Buy"), "of bad news")
    assert result["call"] == "Hold off" and result["proven"] is False
    assert advice.apply_news(answer("Hold", True), "of bad news")["call"] == "Hold and review"
    assert advice.apply_news(answer("Don't buy"), "of bad news")["call"] == "Don't buy"
    assert advice.apply_news(answer("Buy"), None)["call"] == "Buy"


def test_a_holding_gets_a_warning_not_a_forced_sale():
    result = advice.keep_or_sell(
        price=100.0,
        stop=90.0,
        sell_by=None,
        today=NOW.date(),
        stale=False,
        rank=0.8,
        previous_rank=0.8,
        blocked=None,
        bearish_candle=None,
        below_50=False,
        news_warning="of bad news",
    )
    assert result["call"] == "Check the news"


def add_news(engine, subject, items):
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://fixture.test', now(), 'delayed' FROM data_sources
                   WHERE name = 'Publisher news feeds' RETURNING id"""
            )
        ).scalar()
        for item in items:
            conn.execute(
                text(
                    """INSERT INTO news_articles (fetch_id, subject, url, title, domain, seen_at)
                       VALUES (:f, :s, :u, :t, :d, :w)"""
                ),
                {
                    "f": fetch,
                    "s": subject,
                    "u": item["url"] + item["title"],
                    "t": item["title"],
                    "d": item["domain"],
                    "w": NOW,
                },
            )


def test_industry_news_reaches_its_stocks_and_a_broad_theme_reaches_industries(engine):
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank, sic)
                   VALUES ('AAA', 1, 'Fixture Chips', 'NASDAQ', 1, 3674),
                          ('BBB', 2, 'Fixture Bank', 'NYSE', 2, 6021)"""
            )
        )
    add_news(engine, "AI and technology", BAD)
    found = news_watch.stock_warnings(engine, NOW.date())
    assert "the Chips industry" in found["AAA"]
    assert "BBB" not in found
    assert news_watch.record(engine, NOW.date()) >= 1
    assert queries.screener(engine) == []
