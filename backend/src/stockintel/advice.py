"""Factor leans and position tracking. Fixed rules on stored numbers.

The price a stock was bought at says nothing about where it goes next, so it never changes
a buy or sell call. It changes the profit, the break-even and the owner's own plan.
"""

from stockintel.backtest import COST_BPS, MIN_Z
from stockintel.factors import NAMES

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
    "value": 1,
    "size": -1,
    "profitability": 1,
    "investment": -1,
    "accruals": -1,
    "issuance": -1,
    "earnings_drift": 1,
    "insider": 1,
}


def lean_for(percentile: int | None, direction: int | None) -> str:
    if percentile is None or direction is None:
        return "No lean"
    if percentile >= HIGH:
        return "Buy" if direction > 0 else "Sell"
    if percentile <= LOW:
        return "Sell" if direction > 0 else "Buy"
    return "No lean"


def factor_leans(drivers: list[dict], tests: dict[str, dict]) -> dict:
    """Which way each factor leans for one stock, and how strong the evidence is."""
    rows = []
    for item in drivers:
        factor, percentile = item["factor"], item["percentile"]
        test = tests.get(factor)
        proven = test is not None and abs(test["t_stat"]) >= MIN_Z
        paper = PAPER_DIRECTION.get(factor)
        if proven:
            direction = 1 if test["spread"] > 0 else -1
            evidence = "Passed testing in this app"
        elif test is not None:
            direction = paper
            evidence = "Paper only: failed testing in this app"
        else:
            direction = paper
            evidence = "Paper only: not tested in this app yet"
        if direction is None:
            evidence = "No expected direction"
        rows.append(
            {
                "factor": factor,
                "name": NAMES[factor],
                "percentile": percentile,
                "lean": lean_for(percentile, direction),
                "evidence": evidence,
                "proven": proven,
                "t_stat": None if test is None else test["t_stat"],
                "spread": None if test is None else test["spread"],
            }
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
