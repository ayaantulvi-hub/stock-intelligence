"""Two separate answers for one stock: a short trade, and a long-term investment."""

import pandas as pd

from stockintel import candles
from stockintel.stops import average_true_range

HOLD_DAYS = 5
NO_TRADE = "No trade"


def _found(frame: pd.DataFrame, tests: dict) -> list[dict]:
    if len(frame) < 12:
        return []
    last = candles.detect(frame).iloc[-1]
    output = []
    for item in candles.PATTERNS:
        if not last[item.id]:
            continue
        test = tests.get(item.id)
        recent = frame.iloc[-item.candles :]
        output.append(
            {
                "id": item.id,
                "name": item.name,
                "direction": item.direction,
                "meaning": item.meaning,
                "proven": candles.proven(test),
                "failed": bool(test and test["extra_return"] <= 0),
                "signals": test["signals"] if test else None,
                "win_rate": test["win_rate"] if test else None,
                "extra_return": test["extra_return"] if test else None,
                "cancel": float(
                    recent["low"].min() if item.direction == candles.BULL else recent["high"].max()
                ),
            }
        )
    return output


def trade(frame: pd.DataFrame, tests: dict, stale: bool, earnings_in: int | None) -> dict:
    """A trade of up to five days, from today's candle patterns."""

    def answer(call, reason, kind="neutral", exits=None, proven=False):
        return {
            "call": call,
            "reason": reason,
            "kind": kind,
            "proven": proven,
            "hold": exits["hold"] if exits else None,
            "stop": exits["stop"] if exits else None,
            "target": exits["target"] if exits else None,
            "patterns": patterns,
        }

    patterns = _found(frame, tests)
    if stale:
        return answer("Wait", "The latest prices aren't in yet.")
    if earnings_in is not None and 0 <= earnings_in <= 1:
        return answer(NO_TRADE, "Results are due, and candles say nothing about them.")
    live = [
        item for item in patterns if item["direction"] != candles.NEUTRAL and not item["failed"]
    ]
    ups = [item for item in live if item["direction"] == candles.BULL]
    downs = [item for item in live if item["direction"] == candles.BEAR]
    if not patterns:
        return answer(NO_TRADE, "No candle pattern today.")
    if not live:
        return answer(NO_TRADE, "Today's pattern hasn't worked in testing, or shows no direction.")
    if ups and downs:
        return answer(NO_TRADE, "Today's patterns disagree.")
    side = ups or downs
    tested = any(item["proven"] for item in side)
    best = next((item for item in side if item["proven"]), side[0])
    price = float(frame["close"].iloc[-1])
    atr = float(average_true_range(frame).iloc[-1])
    if ups:
        stop = min(best["cancel"], price - atr)
        exits = {"hold": HOLD_DAYS, "stop": stop, "target": price + 2 * (price - stop)}
        call = "Buy for a short trade" if tested else "Leans buy, short trade"
        return answer(call, f"{best['name']}: {best['meaning']}", "buy", exits, tested)
    stop = max(best["cancel"], price + atr)
    exits = {"hold": HOLD_DAYS, "stop": stop, "target": price - 2 * (stop - price)}
    call = "Sell or avoid for now" if tested else "Leans sell, short trade"
    return answer(call, f"{best['name']}: {best['meaning']}", "sell", exits, tested)


LONG_LENSES = (
    "Is the business getting healthier?",
    "Could it go bust?",
    "Is it a good business?",
    "Is it cheap?",
    "Is there room for error?",
)


def invest(review: dict | None) -> dict:
    """An investment of months to years, from the business and its price."""
    if not review:
        return {"call": "Not verified", "reason": "No company review yet.", "kind": "neutral"}
    lenses = [item for item in review["lenses"] if item["name"] in LONG_LENSES]
    known = [item for item in lenses if item["verdict"] != "unknown"]
    good = [item["name"] for item in known if item["verdict"] == "good"]
    bad = [item["name"] for item in known if item["verdict"] == "bad"]
    if review.get("blocked"):
        return {
            "call": "Avoid for now",
            "reason": f"Serious concern: {review['blocked']}.",
            "kind": "sell",
            "hold": None,
        }
    if len(known) < 3:
        return {
            "call": "Not verified",
            "reason": "Too few company figures to judge it as an investment.",
            "kind": "neutral",
            "hold": None,
        }
    score = len(good) - len(bad)
    if score >= 2:
        call, kind, hold = "Good to buy and keep", "buy", "Keep for years while the checks hold."
    elif score <= -2:
        call, kind, hold = "Not a long-term buy", "sell", "Don't plan to keep it for years."
    else:
        call, kind, hold = (
            "Fine to hold, wait to buy",
            "neutral",
            "Review after each yearly report.",
        )
    return {
        "call": call,
        "reason": f"{len(good)} of {len(known)} company checks pass and {len(bad)} fail.",
        "kind": kind,
        "hold": hold,
    }
