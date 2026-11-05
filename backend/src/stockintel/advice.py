"""Factor leans and position tracking. Fixed rules on stored numbers.

The price a stock was bought at says nothing about where it goes next, so it never changes
a buy or sell call. It changes the profit, the break-even and the owner's own plan.
"""

from stockintel.backtest import COST_BPS, MIN_Z
from stockintel.factors import HIGH_MEANS, NAMES

HIGH = 70
LOW = 30

# Direction each paper reports: 1 means higher readings did better, -1 worse.
PAPER_DIRECTION = {
    "mom_12_1": 1,
    "mom_6_1": 1,
    "reversal_1m": -1,
    "reversal_5d": -1,
    "high_52w": 1,
    "vol_60": -1,
    "vol_20": -1,
    "beta": -1,
    "max_ret": -1,
    "illiquidity": 1,
    "above_200": 1,
    "sector_value": 1,
    "sector_profit": 1,
    "sector_momentum": 1,
    "chart_pattern": 1,
    "value": 1,
    "size": -1,
    "profitability": 1,
    "investment": -1,
    "accruals": -1,
    "issuance": -1,
    "earnings_drift": 1,
    "insider": 1,
    "insider_cluster": 1,
    "fscore": 1,
}


CLUSTER_BUYERS = 3

# The stock list is today's largest companies, so past small or wild stocks in it are the
# ones that went on to win. A pass for these factors is likely that bias, not a real effect.
SURVIVORSHIP_SUSPECT = {
    "size",
    "vol_60",
    "vol_20",
    "max_ret",
    "beta",
    "illiquidity",
    "dollar_volume",
}


def lean_for(percentile: int | None, direction: int | None) -> str:
    if percentile is None or direction is None:
        return "No lean"
    if percentile >= HIGH:
        return "Buy" if direction > 0 else "Sell"
    if percentile <= LOW:
        return "Sell" if direction > 0 else "Buy"
    return "No lean"


def reading_meaning(factor: str, percentile: int, lean: str, proven: bool) -> str:
    """What one factor reading says about this stock, and why it matters."""
    high = HIGH_MEANS.get(factor, "")
    if percentile >= HIGH:
        text = f"{high}."
    elif percentile <= LOW:
        text = f"The opposite of: {high.lower()}."
    else:
        return "Close to the middle, so it tells you little either way."
    if lean == "No lean":
        return text
    side = "better" if lean == "Buy" else "worse"
    if proven:
        return f"{text} Stocks like this did {side} in this app's tests."
    return f"{text} Research found stocks like this tended to do {side}, unproven here."


def factor_leans(drivers: list[dict], tests: dict[str, dict]) -> dict:
    """Which way each factor leans for one stock, and how strong the evidence is."""
    rows = []
    for item in drivers:
        factor, percentile = item["factor"], item["percentile"]
        test = tests.get(factor)
        passed = test is not None and abs(test["t_stat"]) >= MIN_Z
        suspect = passed and factor in SURVIVORSHIP_SUSPECT
        proven = passed and not suspect
        paper = PAPER_DIRECTION.get(factor)
        if proven:
            direction = 1 if test["spread"] > 0 else -1
            evidence = "Passed testing in this app"
        elif suspect:
            direction = None
            evidence = "Result distrusted: likely caused by the stock list"
        elif test is not None:
            direction = paper
            evidence = "Paper only: failed testing in this app"
        else:
            direction = paper
            evidence = "Paper only: not tested in this app yet"
        if direction is None and not suspect:
            evidence = "No expected direction"
        rows.append(
            {
                "factor": factor,
                "name": NAMES[factor],
                "percentile": percentile,
                "lean": lean_for(percentile, direction),
                "evidence": evidence,
                "meaning": "",
                "proven": proven,
                "t_stat": None if test is None else test["t_stat"],
                "spread": None if test is None else test["spread"],
            }
        )
    for row in rows:
        row["meaning"] = reading_meaning(
            row["factor"], row["percentile"], row["lean"], row["proven"]
        )
    order = {"Buy": 0, "Sell": 1, "No lean": 2}
    rows.sort(key=lambda row: (order[row["lean"]], not row["proven"]))

    def count(lean: str, proven: bool) -> int:
        return sum(row["lean"] == lean and row["proven"] == proven for row in rows)

    return {
        "factors": rows,
        "proven_buy": count("Buy", True),
        "proven_sell": count("Sell", True),
        "paper_buy": count("Buy", False),
        "paper_sell": count("Sell", False),
    }


def overall(action: str, rank: float | None) -> dict:
    """The decision, plus the model's lean across all factors, clearly marked if unproven."""
    if action in {"Buy candidate", "Sell candidate"}:
        return {"decision": action, "lean": action.split()[0], "proven": True, "rank": rank}
    if rank is None:
        lean = "No lean"
    elif rank >= 0.7:
        lean = "Buy"
    elif rank <= 0.3:
        lean = "Sell"
    else:
        lean = "Mixed"
    return {"decision": action, "lean": lean, "proven": False, "rank": rank}


SELL_RANK = 0.3


def keep_or_sell(
    *,
    price: float | None,
    stop: float | None,
    sell_by,
    today,
    stale: bool,
    rank: float | None,
    previous_rank: float | None,
    blocked: str | None,
    bearish_candle: str | None,
    below_50: bool | None,
    news_warning: str | None = None,
) -> dict:
    """One answer per holding, each day. These are rules, so they can't know what comes next."""

    def answer(call, reason, kind="neutral"):
        return {"call": call, "reason": reason, "kind": kind}

    if price is None or stale:
        return answer("Wait", "Today's prices aren't in yet. Check again after the next update.")
    if stop and price <= stop:
        return answer("Sell now", f"It reached your stop of {stop:.2f}.", "sell")
    if sell_by and today >= sell_by:
        return answer("Sell now", f"Your planned sell date of {sell_by} has arrived.", "sell")
    if blocked:
        return answer("Sell now", f"Serious concern: {blocked}.", "sell")
    # One low reading can be noise, so the ranking has to stay low for two forecasts.
    if rank is not None and previous_rank is not None and max(rank, previous_rank) <= SELL_RANK:
        return answer(
            "Sell now",
            f"The model has ranked it in the bottom {SELL_RANK * 100:.0f}% of stocks "
            "two forecasts in a row.",
            "sell",
        )
    if bearish_candle and below_50:
        return answer(
            "Sell now",
            f"{bearish_candle}, and the price is below its 50-day average.",
            "sell",
        )
    if news_warning:
        return answer(
            "Check the news", f"Keep for now, but look at this because {news_warning}.", "sell"
        )
    reason = "No warning signs today."
    if sell_by:
        reason += f" Planned sell date: {sell_by}."
    return answer("Keep", reason, "buy")


def decision(action: str | None, rank: float | None, stale: bool, position: dict | None) -> dict:
    """One plain answer for this stock, adapted to whether it is owned.

    `proven` is true only when the call rests on a test the model passed. A stop or target
    is the owner's own plan, so those are the owner's rules rather than a forecast.
    """
    owned = position is not None and position.get("profit") is not None

    def answer(call, reason, proven=False, kind="neutral"):
        return {"call": call, "reason": reason, "proven": proven, "kind": kind, "owned": owned}

    if stale:
        return answer("Wait", "The latest prices aren't in yet, so no call can be made.")
    if owned:
        stop, target, price = position["stop_price"], position["target_price"], position["price"]
        if stop and price <= stop:
            return answer(
                "Sell",
                f"It reached your stop of {stop:.2f}. This is the plan you set.",
                kind="sell",
            )
        if target and price >= target:
            return answer(
                "Sell or take some profit",
                f"It reached your target of {target:.2f}. This is the plan you set.",
                kind="buy",
            )
    if action is None:
        return answer("Hold" if owned else "Wait", "There's no forecast for this stock yet.")
    if action == "Sell candidate":
        return answer(
            "Sell" if owned else "Don't buy",
            "The tested model ranks it in its bottom 10%.",
            True,
            "sell",
        )
    if action == "Buy candidate":
        return answer(
            "Hold" if owned else "Buy", "The tested model ranks it in its top 10%.", True, "buy"
        )
    if action == "No action":
        return answer(
            "Hold" if owned else "Wait",
            "The tested model doesn't rank it near the top or bottom.",
            True,
        )
    lean = overall(action, rank)["lean"]
    if lean == "Buy":
        return answer(
            "Hold" if owned else "Leans buy",
            "The model ranks it well, but hasn't passed testing.",
            kind="buy",
        )
    if lean == "Sell":
        return answer(
            "Hold and review" if owned else "Leans don't buy",
            "The model ranks it poorly, but hasn't passed testing.",
            kind="sell",
        )
    return answer("Hold" if owned else "Wait", "The model has no clear lean on this stock.")


# Left out of the short reasons: general reminders, and trend, which the cards already cover.
SKIP_CHECKS = {"Data", "Tested edge", "Your exit plan", "Concentration", "Long-term trend"}


def next_step(call: str, levels: dict | None, position: dict | None) -> str:
    """One concrete thing to do, with prices where they exist."""
    stop = (position or {}).get("stop_price") or (levels or {}).get("stop")
    target = (position or {}).get("target_price") or (levels or {}).get("target")
    exits = (
        f"Sell if it falls to {stop:.2f}. Take profit around {target:.2f}."
        if stop and target
        else "Set a sell target and a stop first."
    )
    if call == "Hold off":
        return "Don't buy for now. Read the reason above, then look at the next stock on the list."
    if call == "Wait":
        return "Do nothing for now, and check again after the next update."
    if call in {"Buy", "Leans buy"}:
        return f"If you decide to buy, start small. {exits}"
    if call in {"Don't buy", "Leans don't buy"}:
        return "Skip this one for now, and look at the stronger stocks on the home page."
    if call == "Sell":
        return "Sell your position, or tell the journal why you're staying in."
    if call == "Sell or take some profit":
        return "Decide whether to sell all or part. You reached the price you planned."
    if call == "Hold and review":
        return f"You don't need to act today, but check the reasons below. {exits}"
    return f"Keep holding. {exits}"


def apply_experts(answer: dict, review: dict | None) -> dict:
    """Serious trouble overrides a buy. This is a written rule, not a tested edge."""
    blocked = review.get("blocked") if review else None
    if not blocked:
        return answer
    if answer["call"] in {"Buy", "Leans buy"}:
        return {
            **answer,
            "call": "Hold off",
            "reason": f"The model likes it, but hold off because {blocked}.",
            "proven": False,
            "kind": "neutral",
        }
    if answer["owned"] and answer["call"] == "Hold":
        return {
            **answer,
            "call": "Hold and review",
            "reason": f"Review this holding because {blocked}.",
            "proven": False,
            "kind": "sell",
        }
    return answer


def apply_news(answer: dict, warning: str | None) -> dict:
    """Bad news stops a buy. It's a caution rule, so it never turns anything into a buy."""
    if not warning:
        return answer
    if answer["call"] in {"Buy", "Leans buy"}:
        return {
            **answer,
            "call": "Hold off",
            "reason": f"The model likes it, but hold off because {warning}.",
            "proven": False,
            "kind": "neutral",
        }
    if answer["owned"] and answer["call"] == "Hold":
        return {
            **answer,
            "call": "Hold and review",
            "reason": f"Review this holding because {warning}.",
            "proven": False,
            "kind": "sell",
        }
    return answer


def brief(
    answer: dict,
    lines: list[dict],
    checks: list[dict],
    levels: dict | None,
    position: dict | None,
    review: dict | None = None,
) -> dict:
    """The decision, up to three reasons each way, and one next step."""
    lenses = (review or {}).get("lenses", [])
    good = [f"{item['name']} {item['reason']}" for item in lenses if item["verdict"] == "good"]
    bad = [f"{item['name']} {item['reason']}" for item in lenses if item["verdict"] == "bad"]
    good += [line["text"] for line in lines if line["tone"] == "good"]
    bad += [line["text"] for line in lines if line["tone"] == "bad"]
    good += [
        check["text"]
        for check in checks
        if check["state"] == "pass" and check["topic"] not in SKIP_CHECKS
    ]
    bad += [
        check["text"]
        for check in checks
        if check["state"] == "caution" and check["topic"] not in SKIP_CHECKS
    ]
    return {
        **answer,
        "reasons_for": good[:3],
        "reasons_against": bad[:3],
        "next_step": next_step(answer["call"], levels, position),
    }


def position_view(position: dict, price: float, action: str, cases: list[dict]) -> dict:
    """Profit, break-even and the owner's plan against the latest close."""
    shares, paid = position["shares"], position["buy_price"]
    # Round-trip trading costs. An assumption, as in the backtests.
    break_even = paid * (1 + COST_BPS / 10000)
    target, stop = position.get("target_price"), position.get("stop_price")
    if stop is not None and price <= stop:
        plan = f"Your stop of {stop:.2f} has been reached."
    elif target is not None and price >= target:
        plan = f"Your target of {target:.2f} has been reached."
    elif target is None and stop is None:
        plan = "You have not set a target or a stop yet."
    else:
        plan = "The price is between your stop and your target."
    if action == "Sell candidate":
        call = "The tested model ranks this stock in its bottom 10%, whatever you paid."
    elif action == "Buy candidate":
        call = "The tested model ranks this stock in its top 10%. It gives no reason to sell."
    elif action == "No action":
        call = "The tested model does not rank this near the top or bottom."
    else:
        call = "No sell call: testing has not shown the model can time this."
    return {
        **position,
        "price": price,
        "cost": shares * paid,
        "worth": shares * price,
        "profit": shares * (price - paid),
        "profit_percent": (price / paid - 1) * 100,
        "break_even": break_even,
        "above_break_even": price >= break_even,
        "plan": plan,
        "call": call,
        "cases": [
            {"name": case["name"], "value": case["value"], "from_cost": case["value"] / paid - 1}
            for case in cases
        ],
    }


MAX_SINGLE_STOCK = 0.10
MIN_SAFETY = 0.15
MAX_DEBT_TO_EQUITY = 1.0


CHECK_MEANINGS = {
    ("Data", "caution"): "Decisions on old prices can be wrong, so wait for the update.",
    ("Tested edge", "caution"): "Nothing here proves this stock will beat the market.",
    ("Tested edge", "pass"): "The ranking has held up in testing, but it can still be wrong.",
    ("Long-term trend", "pass"): "You would be going with the bigger direction.",
    ("Long-term trend", "caution"): "Falling stocks can keep falling, so a low price isn't "
    "automatically a bargain.",
    ("Margin of safety", "pass"): "If the estimate is somewhat wrong, you still have a cushion.",
    ("Margin of safety", "caution"): "If the estimate is wrong, there's little cushion.",
    ("Downside", "pass"): "Even the cautious case is above today's price.",
    ("Downside", "caution"): "If things go less well, the shares could be worth less than today.",
    ("Debt", "pass"): "Lower debt gives a company more room in a bad year.",
    ("Debt", "caution"): "More debt raises the risk in a downturn, though normal levels differ "
    "by industry.",
    ("Insiders", "pass"): "People running the company put in more than they took out. They can "
    "still be wrong.",
    ("Insiders", "caution"): "Insiders sell for many reasons, like tax, so this is a weak warning.",
    ("Earnings", "pass"): "A report isn't likely for a while, so that risk is lower.",
    ("Earnings", "caution"): "Prices can jump either way on a report, so holding through one is "
    "riskier.",
    ("Your exit plan", "pass"): "You've decided in advance, which helps you avoid panic.",
    ("Your exit plan", "caution"): "Without a plan, it's easier to panic or hold a loser too long.",
    ("Concentration", "pass"): "One bad result won't sink your holdings.",
    ("Concentration", "caution"): "One bad company could do real damage to your total.",
}


def _check(topic: str, state: str, text: str) -> dict:
    meaning = CHECK_MEANINGS.get((topic, state), "This couldn't be checked, so look into it first.")
    return {"topic": topic, "state": state, "text": text, "meaning": meaning}


def _metric(report: dict, name: str) -> float | None:
    for item in report.get("metrics", []):
        if item["name"] == name:
            return item["value"]
    return None


def checklist(
    *,
    stale: bool,
    latest_bar=None,
    expected=None,
    action: str | None,
    above_200: bool | None,
    report: dict,
    insider_net: float | None,
    last_earnings_days: int | None,
    insider_buyers: int = 0,
    serious_events: list[str] | None = None,
    position: dict | None,
    portfolio_share: float | None,
) -> list[dict]:
    """A pre-trade review. Pass, Caution or Not verified, never added into a score."""
    checks = [
        _check(
            "Data",
            "caution" if stale else "pass",
            (
                f"The latest price here is {latest_bar}, but {expected} should be in. "
                "The update has not reached this stock yet, so signals are blocked."
                if stale
                else "Prices are up to date."
            ),
        )
    ]
    if action in {"Buy candidate", "Sell candidate"}:
        checks.append(_check("Tested edge", "pass", "The model passed testing."))
    else:
        checks.append(
            _check("Tested edge", "caution", "No proven edge, so any trade rests on your own view.")
        )
    if above_200 is None:
        checks.append(_check("Long-term trend", "unknown", "Not enough price history."))
    else:
        checks.append(
            _check(
                "Long-term trend",
                "pass" if above_200 else "caution",
                "Above the 200-day average."
                if above_200
                else "Below the 200-day average: you would be buying against the long-term trend.",
            )
        )
    cases = {case["name"]: case for case in report.get("cases", [])}
    if "Base" not in cases:
        checks.append(_check("Margin of safety", "unknown", "No value estimate is available."))
    else:
        gap = cases["Base"]["against_price"]
        checks.append(
            _check(
                "Margin of safety",
                "pass" if gap >= MIN_SAFETY else "caution",
                f"Base value is {gap * 100:+.0f}% against the price. "
                "A 15% cushion allows for the estimate being wrong.",
            )
        )
    if "Bear" in cases:
        bear = cases["Bear"]["against_price"]
        checks.append(
            _check(
                "Downside",
                "pass" if bear >= 0 else "caution",
                f"If the Bear assumptions came true, value is {bear * 100:+.0f}% against the price.",
            )
        )
    debt = _metric(report, "Debt to equity")
    if debt is None:
        checks.append(_check("Debt", "unknown", "Debt figures are not available."))
    else:
        safe = 0 <= debt <= MAX_DEBT_TO_EQUITY
        checks.append(
            _check(
                "Debt", "pass" if safe else "caution", f"Long-term debt is {debt:.2f} times equity."
            )
        )
    if insider_net is None:
        checks.append(_check("Insiders", "unknown", "No open-market insider trades stored."))
    else:
        checks.append(
            _check(
                "Insiders",
                "pass" if insider_net >= 0 else "caution",
                f"Insiders were net {'buyers' if insider_net >= 0 else 'sellers'} of "
                f"${abs(insider_net):,.0f} in 90 days, leaving out planned sales."
                + (
                    f" {insider_buyers} different insiders bought, which research finds "
                    "more telling than one person buying."
                    if insider_buyers >= CLUSTER_BUYERS
                    else ""
                ),
            )
        )
    if serious_events:
        checks.append(
            _check("Company news", "caution", "In the last 90 days: " + "; ".join(serious_events))
        )
    elif serious_events is not None:
        checks.append(
            _check("Company news", "pass", "No serious events in its filings in the last 90 days.")
        )
    if last_earnings_days is None:
        checks.append(_check("Earnings", "unknown", "The last report date is not stored."))
    else:
        soon = last_earnings_days >= 75
        checks.append(
            _check(
                "Earnings",
                "caution" if soon else "pass",
                f"Last quarterly or yearly report was {last_earnings_days} days ago."
                + (" The next could be close, and prices often jump on reports." if soon else ""),
            )
        )
    if position is None:
        checks.append(
            _check("Your exit plan", "caution", "Decide your target and stop before you buy.")
        )
    else:
        ready = position.get("target_price") and position.get("stop_price")
        checks.append(
            _check(
                "Your exit plan",
                "pass" if ready else "caution",
                "Target and stop are set." if ready else "Set both a target and a stop.",
            )
        )
    if portfolio_share is not None:
        checks.append(
            _check(
                "Concentration",
                "pass" if portfolio_share <= MAX_SINGLE_STOCK else "caution",
                f"This is {portfolio_share * 100:.0f}% of the holdings entered here. "
                "A common limit is 10%.",
            )
        )
    return checks
