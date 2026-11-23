"""Run the quant lab studies on stored prices and store the results.

Prints summary figures only (no prices or holdings), so it is safe for public job logs.
Run: python -m stockintel.quant.run [study ...]
"""

import json
import math
import sys
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from stockintel.db import get_engine
from stockintel.quant import engine as bt
from stockintel.quant import studies
from stockintel.quant.data import panels
from stockintel.quant.evaluate import judge


def _clean(value):
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 6)  # NaN becomes null.
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def store(engine: Engine, study: str, variant: str, result: dict, settings: dict) -> None:
    clean = _clean(result)
    period = f"{clean['strategy']['start']} to {clean['strategy']['end']}"
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO quant_results (run_at, study, variant, period, metrics, verdict,
                     settings) VALUES (:at, :study, :variant, :period, :m, :v, :s)"""
            ),
            {
                "at": datetime.now(UTC),
                "study": study,
                "variant": variant,
                "period": period,
                "m": json.dumps(clean),
                "v": clean["verdict"],
                "s": json.dumps(settings),
            },
        )
    s, b = clean["strategy"], clean["baseline"]
    print(
        f"QUANT {study}/{variant}: {clean['verdict']} | t={clean['choice_t']} hold-out "
        f"gain={clean['holdout_gain_daily']} | Sharpe {s['sharpe']} vs {b['sharpe']} | "
        f"max drawdown {s['max_drawdown']} vs {b['max_drawdown']} | {period}"
    )


def ma_crossover(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None)
    baseline = bt.run(studies.equal_weight(mask), returns)
    strategy = bt.run(studies.ma_crossover(prices, mask), returns)
    settings = {"fast": 50, "slow": 200, "cost_bps": bt.COST_BPS, "stocks": int(mask.any().sum())}
    store(engine, "ma_crossover", "50/200", judge(strategy.net, baseline.net), settings)


STUDIES = {"ma_crossover": ma_crossover}
MIN_STOCKS = 50


def main() -> None:
    engine = get_engine()
    prices, mask = panels(engine)
    # Start once at least 50 stocks are tradeable, so early years aren't a handful of names.
    count = mask.sum(axis=1)
    needed = min(MIN_STOCKS, int(count.max()))
    if needed < 10:
        raise SystemExit(f"Not verified: only {int(count.max())} tradeable stocks, too few to test")
    first = count[count >= needed].index.min()
    prices, mask = prices[prices.index >= first], mask[mask.index >= first]
    for name in sys.argv[1:] or list(STUDIES):
        STUDIES[name](engine, prices, mask)


if __name__ == "__main__":
    main()
