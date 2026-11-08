"""Did the caution rules help? Stocks a rule blocked against stocks it didn't, 20 trading days on.

The rules: an expert check blocking a buy, and a news warning. They only ever stop buys, so the
question is whether the stocks they stopped really did worse. Until enough blocked stocks have
had 20 days to play out, the answer is "Not enough history yet".
"""

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel.news_watch import industry_of

HOLD = 20
MIN_BLOCKED = 30
MIN_T = 2.0


def forward_returns(engine: Engine) -> pd.DataFrame:
    """Each stock's return over the next 20 trading days from each review date, split-adjusted."""
    query = """SELECT DISTINCT ON (security_id, market_date) security_id, market_date, close,
                 split_factor FROM price_bars WHERE market_date >= :since
               ORDER BY security_id, market_date, id DESC"""
    with engine.connect() as conn:
        first = conn.execute(text("SELECT min(review_date) FROM expert_reviews")).scalar()
        if first is None:
            return pd.DataFrame()
        rows = pd.DataFrame([r._mapping for r in conn.execute(text(query), {"since": first})])
    if rows.empty:
        return rows
    out = []
    for security, group in rows.groupby("security_id"):
        group = group.sort_values("market_date")
        # Undo later splits so a split doesn't look like a crash.
        factor = group["split_factor"].iloc[::-1].cumprod().iloc[::-1].shift(-1).fillna(1.0)
        close = group["close"] / factor
        ahead = close.shift(-HOLD) / close - 1
        out.append(
            pd.DataFrame(
                {"security_id": security, "day": group["market_date"].values, "ret": ahead.values}
            )
        )
    return pd.concat(out).dropna()


def compare(blocked: np.ndarray, others: np.ndarray) -> dict:
    result = {
        "blocked": len(blocked),
        "blocked_mean": float(blocked.mean()) if len(blocked) else None,
        "others": len(others),
        "others_mean": float(others.mean()) if len(others) else None,
        "t": None,
    }
    if len(blocked) < MIN_BLOCKED or len(others) < MIN_BLOCKED:
        result["verdict"] = "Not enough history yet"
        return result
    gap = blocked.mean() - others.mean()
    se = np.sqrt(blocked.var(ddof=1) / len(blocked) + others.var(ddof=1) / len(others))
    result["t"] = float(gap / se) if se > 0 else None
    if result["t"] is not None and result["t"] <= -MIN_T:
        result["verdict"] = "Helped: blocked stocks did worse"
    elif result["t"] is not None and result["t"] >= MIN_T:
        result["verdict"] = "Hurt: blocked stocks did better"
    else:
        result["verdict"] = "No difference shown"
    return result


def run(engine: Engine) -> dict:
    returns = forward_returns(engine)
    with engine.connect() as conn:
        reviews = pd.DataFrame(
            [
                r._mapping
                for r in conn.execute(
                    text(
                        "SELECT security_id, review_date AS day, blocked IS NOT NULL AS blocked "
                        "FROM expert_reviews"
                    )
                )
            ]
        )
        warned = pd.DataFrame(
            [r._mapping for r in conn.execute(text("SELECT day, subject FROM news_warnings"))]
        )
        stocks = pd.DataFrame(
            [r._mapping for r in conn.execute(text("SELECT id, ticker, sic FROM securities"))]
        )
    results = {}
    if returns.empty or reviews.empty:
        empty = np.array([])
        results = {"Expert checks": compare(empty, empty), "News warnings": compare(empty, empty)}
    else:
        reviews = reviews.drop_duplicates(["security_id", "day"], keep="last")
        joined = reviews.merge(returns, on=["security_id", "day"])
        results["Expert checks"] = compare(
            joined.loc[joined["blocked"], "ret"].to_numpy(),
            joined.loc[~joined["blocked"], "ret"].to_numpy(),
        )
        flagged = set()
        if not warned.empty:
            for row in stocks.itertuples():
                subjects = {row.ticker, industry_of(row.sic)}
                for item in warned[warned["subject"].isin(subjects)].itertuples():
                    flagged.add((row.id, item.day))
        base = returns.assign(
            warned=[(s, d) in flagged for s, d in zip(returns["security_id"], returns["day"])]
        )
        results["News warnings"] = compare(
            base.loc[base["warned"], "ret"].to_numpy(), base.loc[~base["warned"], "ret"].to_numpy()
        )
    with engine.begin() as conn:
        for rule, r in results.items():
            conn.execute(
                text(
                    """INSERT INTO override_tests (rule, blocked, blocked_mean, others,
                         others_mean, t_stat, verdict)
                       VALUES (:rule, :blocked, :bm, :others, :om, :t, :verdict)"""
                ),
                {
                    "rule": rule,
                    "blocked": r["blocked"],
                    "bm": r["blocked_mean"],
                    "others": r["others"],
                    "om": r["others_mean"],
                    "t": r["t"],
                    "verdict": r["verdict"],
                },
            )
    return results


def latest(engine: Engine) -> list[dict]:
    query = """SELECT DISTINCT ON (rule) rule, run_at, blocked, blocked_mean, others, others_mean,
                 t_stat, verdict FROM override_tests ORDER BY rule, id DESC"""
    with engine.connect() as conn:
        return [dict(r._mapping) for r in conn.execute(text(query))]


if __name__ == "__main__":
    import json

    from stockintel.db import get_engine

    print(json.dumps(run(get_engine()), indent=2, default=str))
