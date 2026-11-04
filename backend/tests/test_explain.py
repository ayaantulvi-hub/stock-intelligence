"""Plain-English lines. Every input here is a TEST FIXTURE."""

from stockintel.explain import story

FACTS = {
    "close": 265.64,
    "average_50": 250.0,
    "average_200": 280.0,
    "resistance": 269.79,
    "support": 261.41,
    "above_200": False,
    "above_50": True,
    "rsi": 74.2,
    "rsi_state": "Overbought",
    "percent_to_resistance": 1.6,
    "percent_to_support": -1.6,
}


def text(lines):
    return " ".join(line["text"] for line in lines)


def test_no_data_says_nothing():
    assert story(None, [], False, None) == []


def test_states_facts_in_plain_english():
    result = text(story(FACTS, [], False, None))
    assert "Down: the price is below its 200-day average." in result
    assert "Up: the price is above its 50-day average." in result
    assert "Stretched upward" in result
    assert "1.6% below a ceiling" in result


def test_unknown_values_are_left_out():
    facts = {**FACTS, "above_200": None, "average_200": None, "rsi": None, "rsi_state": None}
    topics = [line["topic"] for line in story(facts, [], False, None)]
    assert "Long-term trend" not in topics
    assert "Momentum" not in topics


def test_signal_says_it_is_unproven_and_gives_its_cancel_level():
    signal = {
        "name": "Breakout",
        "label": "Unproven",
        "detail": "Closed above resistance",
        "cancellation_level": 261.41,
        "market_date": "2026-11-02",
    }
    line = story(FACTS, [signal], False, None)[-1]
    assert "not been tested enough" in line["text"]
    assert "261.41" in line["why"]


def test_blocked_signals_are_stated():
    assert "Blocked" in text(story(FACTS, [], True, None))


def test_never_tells_the_reader_to_buy_or_sell():
    signal = {
        "name": "Golden cross",
        "label": "Bullish",
        "detail": "Crossed",
        "cancellation_level": 1.0,
        "market_date": "2026-11-02",
    }
    forecast = {"range_low": 95.0, "range_high": 105.0, "last_close": 100.0}
    result = text(story(FACTS, [signal], False, forecast)).lower()
    assert "buy" not in result and "sell" not in result


def test_each_judgement_shows_its_numbers_and_where_to_look():
    lines = story(FACTS, [], False, None)
    trend = lines[0]
    assert "265.64" in trend["evidence"] and "280.00" in trend["evidence"]
    assert "-5.1%" in trend["evidence"]
    assert "purple line" in trend["on_chart"]
    prices = next(line for line in lines if line["topic"] == "Key prices")
    assert "269.79" in prices["evidence"] and "261.41" in prices["evidence"]


def test_call_explains_the_test_behind_it():
    test = {
        "edge": False,
        "test_days": 153,
        "first_test": "2015-01-02",
        "last_test": "2026-09-22",
        "stocks": 81,
        "t_stat": -0.8,
        "top_minus_bottom": 0.009,
    }
    line = story(
        FACTS,
        [],
        False,
        {"range_low": 90.0, "range_high": 110.0, "last_close": 100.0},
        {"rank_20d": test},
    )[0]
    assert line["topic"] == "Why this call"
    assert "did not pass" in line["text"]
    assert "153" in line["evidence"] and "-0.8" in line["evidence"]


def test_tested_signal_shows_its_record():
    signal = {
        "name": "MACD cross",
        "label": "Neutral",
        "detail": "Crossed",
        "cancellation_level": 1.0,
        "market_date": "2026-11-02",
        "win_rate": 0.58,
        "sample_size": 12456,
        "baseline_win_rate": 0.582,
    }
    assert "58.0% of 12456" in story(FACTS, [signal], False, None)[-1]["evidence"]


def test_company_profit_is_explained_with_its_numbers():
    history = [
        {"period_end": "2024-12-31", "net_income": 1e9},
        {"period_end": "2025-12-31", "net_income": 1.5e9},
    ]
    line = story(FACTS, [], False, None, {}, history)[0]
    assert line["topic"] == "Company profit"
    assert "$1.5 billion" in line["text"] and "+50%" in line["text"]
    assert line["tone"] == "good"


def test_every_line_says_what_it_means_for_you():
    signal = {
        "name": "Breakout",
        "label": "Unproven",
        "detail": "Closed above resistance",
        "cancellation_level": 1.0,
        "market_date": "2026-11-02",
    }
    forecast = {"range_low": 95.0, "range_high": 105.0, "last_close": 100.0}
    for line in story(FACTS, [signal], True, forecast):
        assert line["meaning"]
