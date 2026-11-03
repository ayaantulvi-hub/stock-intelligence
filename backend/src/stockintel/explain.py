"""Plain-English reading of one stock, built by fixed rules from stored numbers.

No AI writes this text. Each line describes a fact, says why it matters, and says whether
the idea behind it has been tested.
"""


def _line(topic: str, tone: str, text: str, why: str) -> dict:
    return {"topic": topic, "tone": tone, "text": text, "why": why}


def story(
    summary: dict | None, chart_signals: list[dict], blocked: bool, forecast: dict | None
) -> list[dict]:
    if summary is None:
        return []
    lines = []
    above_200, above_50 = summary["above_200"], summary["above_50"]
    if above_200 is not None:
        lines.append(
            _line(
                "Long-term trend",
                "good" if above_200 else "bad",
                "Up: the price is above its 200-day average."
                if above_200
                else "Down: the price is below its 200-day average.",
                "The 200-day average is the mean closing price over about 10 months. "
                "It shows the bigger direction by smoothing out daily noise.",
            )
        )
    if above_50 is not None:
        lines.append(
            _line(
                "Recent trend",
                "good" if above_50 else "bad",
                "Up: the price is above its 50-day average."
                if above_50
                else "Down: the price is below its 50-day average.",
                "The 50-day average is the mean closing price over about 2.5 months.",
            )
        )
    if summary["rsi"] is not None:
        state = summary["rsi_state"]
        text = {
            "Overbought": "Stretched upward: it has risen fast, with RSI at {:.0f}.",
            "Oversold": "Stretched downward: it has fallen fast, with RSI at {:.0f}.",
            "Middle range": "Normal: neither stretched up nor down, with RSI at {:.0f}.",
        }[state]
        lines.append(
            _line(
                "Momentum",
                "neutral",
                text.format(summary["rsi"]),
                "RSI is a 0 to 100 score of how fast the price has moved lately. "
                "Above 70 or below 30 is stretched, but it does not have to reverse.",
            )
        )
    to_resistance = summary["percent_to_resistance"]
    to_support = summary["percent_to_support"]
    if to_resistance is not None or to_support is not None:
        parts = []
        if to_resistance is not None:
            parts.append(
                f"{abs(to_resistance):.1f}% below a ceiling, where it stopped rising before"
            )
        if to_support is not None:
            parts.append(f"{abs(to_support):.1f}% above a floor, where it stopped falling before")
        lines.append(
            _line(
                "Key prices",
                "neutral",
                f"It sits {' and '.join(parts)}.",
                "The ceiling is called resistance and the floor is called support. "
                "Both come from past turning points, and either can break.",
            )
        )
    if forecast:
        low = (forecast["range_low"] / forecast["last_close"] - 1) * 100
        high = (forecast["range_high"] / forecast["last_close"] - 1) * 100
        lines.append(
            _line(
                "Normal daily swing",
                "neutral",
                f"On 9 days in 10 over the past year, it moved between {low:.1f}% and +{high:.1f}%.",
                "This shows how much a position could move in an ordinary day.",
            )
        )
    if blocked:
        lines.append(
            _line(
                "Signals",
                "bad",
                "Blocked, because the latest prices are missing.",
                "Signals on old data could mislead you.",
            )
        )
    for signal in chart_signals:
        tested = {
            "Bullish": "Testing supports it.",
            "Bearish": "Testing supports it.",
            "Neutral": "Testing found no reliable edge.",
            "Forming": "It has not happened yet.",
            "Unproven": "It has not been tested enough to trust.",
        }[signal["label"]]
        lines.append(
            _line(
                signal["name"],
                "neutral",
                f"{signal['detail']}. {tested}",
                f"If the price passes {signal['cancellation_level']:.2f}, this idea has failed.",
            )
        )
    return lines
