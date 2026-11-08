"""One decision path: which caution rules may change a call, and which are only shown.

The ranking makes the call. A caution can override it only once it has been shown to help:
- Expert checks and news warnings: when overrides.py finds that the stocks they stopped
  really did worse ("Helped").
- The market check: when regime.py passes its test and reads "Cautious".
Until then each caution is still shown beside the decision, as something worth knowing.
Safety rules for holdings (a stop hit, a sell-by date) always apply: they are your own plan.
"""

from datetime import date

from sqlalchemy import Engine

from stockintel import experts, news_watch, overrides, regime


def proven(engine: Engine) -> dict[str, bool]:
    results = {row["rule"]: row["verdict"] for row in overrides.latest(engine)}
    return {
        rule: results.get(rule, "").startswith("Helped")
        for rule in ("Expert checks", "News warnings")
    }


def cautions(engine: Engine, today: date) -> dict[str, dict]:
    """Every caution per stock: its reason, which rule it came from, and whether it counts."""
    counts = proven(engine)
    found: dict[str, dict] = {}
    for ticker, reason in experts.stored_blocks(engine).items():
        found[ticker] = {
            "reason": reason,
            "rule": "Expert checks",
            "counts": counts["Expert checks"],
        }
    for ticker, reason in news_watch.stock_warnings(engine, today).items():
        if ticker not in found or not found[ticker]["counts"]:
            found[ticker] = {
                "reason": reason,
                "rule": "News warnings",
                "counts": counts["News warnings"],
            }
    return found


def active(engine: Engine, today: date) -> dict[str, str]:
    """Only the cautions allowed to change a call."""
    return {t: c["reason"] for t, c in cautions(engine, today).items() if c["counts"]}


def market_hold(engine: Engine) -> str | None:
    """A reason to hold off new buys, only if the market check passed its test."""
    check = regime.current(engine)
    if check and check["edge"] and check["state"] == "Cautious":
        return (
            f"The market check is cautious: about {check['chance']:.0%} chance the average stock "
            "rises over the next month."
        )
    return None
