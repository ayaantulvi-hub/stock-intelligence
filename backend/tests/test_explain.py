"""Plain-English lines. Every input here is a TEST FIXTURE."""

from stockintel.explain import story

FACTS = {
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
    facts = {**FACTS, "above_200": None, "rsi": None, "rsi_state": None}
    topics = [line["topic"] for line in story(facts, [], False, None)]
    assert "Long-term trend" not in topics
    assert "Momentum" not in topics


def test_signal_says_it_is_unproven_and_gives_its_cancel_level():
    signal = {
        "name": "Breakout",
        "label": "Unproven",
        "detail": "Closed above resistance",
        "cancellation_level": 261.41,
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
    }
    forecast = {"range_low": 95.0, "range_high": 105.0, "last_close": 100.0}
    result = text(story(FACTS, [signal], False, forecast)).lower()
    assert "buy" not in result and "sell" not in result
