"""Plain-English reading of one stock, built by fixed rules from stored numbers.

No AI writes this text. Each line describes a fact, says why it matters, and says whether
the idea behind it has been tested.
"""


def _line(topic: str, tone: str, text: str, why: str, evidence: str, on_chart: str) -> dict:
    return {
        "topic": topic,
        "tone": tone,
        "text": text,
        "why": why,
        "evidence": evidence,
        "on_chart": on_chart,
    }


MEANINGS = {
    ("Long-term trend", "good"): "You'd be going with the bigger direction, which many investors "
    "prefer. It doesn't mean it will keep rising.",
    ("Long-term trend", "bad"): "You'd be going against the bigger direction. Falling stocks can "
    "keep falling, so a lower price isn't automatically a bargain.",
    ("Recent trend", "good"): "Recent buyers are mostly sitting on gains.",
    ("Recent trend", "bad"): "Recent buyers are mostly sitting on losses, which can bring more "
    "selling.",
    ("Company profit", "good"): "Rising profit supports the share price over time, though much "
    "of it may already be in the price.",
    ("Company profit", "bad"): "Weak profit can pull the share price down, unless investors "
    "expect a recovery.",
}
DEFAULT_MEANINGS = {
    "Momentum": "A stretched stock can keep going, so this alone isn't a reason to act. It does "
    "suggest being careful about chasing the move.",
    "Key prices": "Buying just under a ceiling leaves less room to rise. A floor gives you a "
    "natural place to set a stop.",
    "Normal daily swing": "A move inside this range is ordinary, so it's no reason to panic.",
    "Why this call": "Until this passes, treat every lean on this page as unproven.",
    "Signals": "Wait for fresh prices before acting.",
}


def _meaning(line: dict) -> str:
    return (
        MEANINGS.get((line["topic"], line["tone"]))
        or DEFAULT_MEANINGS.get(line["topic"])
        or "On its own this is weak evidence, so weigh it with everything else."
    )


def _versus(close: float, average: float, name: str) -> str:
    gap = (close / average - 1) * 100
    return f"Last close {close:.2f} against {name} {average:.2f}, a gap of {gap:+.1f}%."


def _money(value: float) -> str:
    size = abs(value)
    sign = "-" if value < 0 else ""
    if size >= 1e9:
        return f"{sign}${size / 1e9:.1f} billion"
    return f"{sign}${size / 1e6:.1f} million"


def company_lines(history: list[dict]) -> list[dict]:
    """The latest yearly results, from SEC filings."""
    rows = [row for row in history if row["net_income"] is not None]
    if not rows:
        return []
    latest = rows[-1]
    income = latest["net_income"]
    text = f"Net income was {_money(income)} in the year to {latest['period_end']}."
    tone = "good" if income > 0 else "bad"
    if len(rows) >= 2 and rows[-2]["net_income"] > 0:
        change = (income / rows[-2]["net_income"] - 1) * 100
        text += f" That is {change:+.0f}% on the year before."
        tone = "good" if change >= 0 else "bad"
    evidence = " ".join(f"{row['period_end']}: {_money(row['net_income'])}." for row in rows)
    return [
        _line(
            "Company profit",
            tone,
            text,
            "Net income is what is left after all costs and tax. "
            "Over long periods, share prices tend to follow profits.",
            f"From yearly SEC filings. {evidence}",
            "This comes from filings, not the chart. See the Long-term tab.",
        )
    ]


def verdict_lines(forecast: dict | None, evaluations: dict[str, dict]) -> list[dict]:
    """Why the What to do box says what it says, using the model's test results."""
    test = evaluations.get("rank_20d")
    if forecast is None or test is None:
        return []
    verdict = "passed" if test["edge"] else "did not pass"
    spread = test["top_minus_bottom"]
    detail = (
        f"Tested on {test['test_days']} separate dates from {test['first_test']} to "
        f"{test['last_test']}, across {test['stocks']} stocks. It needed a test score of "
        f"at least 3.0 and got {test['t_stat']:.1f}."
    )
    if spread is not None:
        detail += (
            f" Its top-ranked stocks beat its bottom-ranked ones by {spread * 100:.1f}% over "
            "20 days after costs, which is not enough on its own."
        )
    return [
        _line(
            "Why this call",
            "neutral",
            f"The 20-day stock ranking {verdict} its test against chance.",
            "A stock is only named to buy or sell if this test is passed.",
            detail,
            "This comes from testing, not from this stock's chart.",
        )
    ]


def story(
    summary: dict | None,
    chart_signals: list[dict],
    blocked: bool,
    forecast: dict | None,
    evaluations: dict[str, dict] | None = None,
    history: list[dict] | None = None,
) -> list[dict]:
    if summary is None:
        return []
    lines = verdict_lines(forecast, evaluations or {}) + company_lines(history or [])
    close = summary["close"]
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
                _versus(close, summary["average_200"], "the 200-day average"),
                "Chart tab: compare the candles with the purple line. "
                + ("The candles sit above it." if above_200 else "The candles sit below it."),
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
                _versus(close, summary["average_50"], "the 50-day average"),
                "Chart tab: compare the candles with the blue line. "
                + ("The candles sit above it." if above_50 else "The candles sit below it."),
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
                f"RSI is {summary['rsi']:.1f}. Stretched means above 70 or below 30.",
                "Chart tab: see the purple line in the RSI panel against the 70 and 30 lines.",
            )
        )
    to_resistance = summary["percent_to_resistance"]
    to_support = summary["percent_to_support"]
    if to_resistance is not None or to_support is not None:
        parts, evidence = [], [f"Last close {close:.2f}."]
        if summary["resistance"] is not None:
            evidence.append(f"Ceiling {summary['resistance']:.2f}.")
        if summary["support"] is not None:
            evidence.append(f"Floor {summary['support']:.2f}.")
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
                " ".join(evidence),
                "Chart tab: the dashed red line is the ceiling and the dashed green line "
                "is the floor. Look for earlier turns at those prices.",
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
                "Worked out from this stock's last 250 daily moves, leaving out the "
                "largest 5% in each direction.",
                "Chart tab: compare the size of the recent candles.",
            )
        )
    if blocked:
        lines.append(
            _line(
                "Signals",
                "bad",
                "Blocked, because the latest prices are missing.",
                "Signals on old data could mislead you.",
                "The newest stored price is older than the last market day.",
                "Chart tab: the latest candle is out of date.",
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
        if signal.get("win_rate") is None:
            record = "No test results for this signal on this timeframe yet."
        else:
            record = (
                f"Won {signal['win_rate'] * 100:.1f}% of {signal['sample_size']} past cases, "
                f"against {signal['baseline_win_rate'] * 100:.1f}% for simply holding."
            )
        lines.append(
            _line(
                signal["name"],
                "neutral",
                f"{signal['detail']}. {tested}",
                f"If the price passes {signal['cancellation_level']:.2f}, this idea has failed.",
                record,
                f"Chart tab: this happened on the latest candle, {signal['market_date']}.",
            )
        )
    for line in lines:
        line["meaning"] = _meaning(line)
    return lines
