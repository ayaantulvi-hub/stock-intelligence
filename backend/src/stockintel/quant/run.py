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
from stockintel.quant import pairs, panic, studies, var, vol
from stockintel.quant.data import industries, market_history, panels, risk_free
from stockintel.quant.evaluate import judge
from stockintel.quant.metrics import summary


def _clean(value):
    if isinstance(value, float):
        return None if math.isnan(value) else round(value, 6)  # NaN becomes null.
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    return value


def monthly_growth(returns: pd.Series) -> list[float]:
    """Growth of $1 at each month end: a small, derived series for the private dashboard."""
    wealth = (1 + returns.fillna(0)).cumprod()
    return [round(float(v), 5) for v in wealth.resample("ME").last()]


def months(index: pd.Index) -> list[str]:
    return [d.strftime("%Y-%m") for d in pd.Series(1, index=index).resample("ME").last().index]


def growth_series(strategy: pd.Series, baseline: pd.Series) -> dict:
    return {
        "months": months(strategy.index),
        "strategy": monthly_growth(strategy),
        "baseline": monthly_growth(baseline.reindex(strategy.index)),
    }


def store(engine: Engine, study: str, variant: str, result: dict, settings: dict) -> None:
    clean = _clean(result)
    period = (
        f"{clean['strategy']['start']} to {clean['strategy']['end']}"
        if "strategy" in clean
        else f"{clean['start']} to {clean['end']}"
    )
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
    if "strategy" in clean:
        s, b = clean["strategy"], clean["baseline"]
        detail = (
            f"t={clean['choice_t']} hold-out gain={clean['holdout_gain_daily']} | Sharpe "
            f"{s['sharpe']} vs {b['sharpe']} | max drawdown {s['max_drawdown']} vs {b['max_drawdown']}"
        )
    else:
        detail = ", ".join(
            f"{k}={v}" for k, v in clean.items() if k not in {"verdict", "start", "end", "series"}
        )
    print(f"QUANT {study}/{variant}: {clean['verdict']} | {detail} | {period}")


def ma_crossover(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None)
    baseline = bt.run(studies.equal_weight(mask), returns)
    strategy = bt.run(studies.ma_crossover(prices, mask), returns)
    settings = {"fast": 50, "slow": 200, "cost_bps": bt.COST_BPS, "stocks": int(mask.any().sum())}
    result = judge(strategy.net, baseline.net)
    result["series"] = growth_series(strategy.net, baseline.net)
    store(engine, "ma_crossover", "50/200", result, settings)


def vol_targeting(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None)
    market = bt.run(studies.equal_weight(mask), returns).net
    rf = risk_free(engine, market.index)
    excess = (market - rf).dropna()
    for kind, label in (
        ("variance", "variance-managed (Moreira-Muir)"),
        ("volatility", "volatility target"),
        ("conditional", "conditional (Bongaerts et al.)"),
        ("ewma", "daily EWMA (Harvey et al.)"),
    ):
        strategy, held = vol.managed(excess, kind)
        baseline = excess.reindex(strategy.index)
        result = judge(strategy, baseline, by="alpha")
        result["average_exposure"] = float(held.mean())
        result["max_exposure"] = float(held.max())
        result["series"] = growth_series(strategy, baseline)
        settings = {
            "window_days": vol.WINDOW,
            "max_leverage": vol.MAX_LEVERAGE,
            "rebalance": "daily" if kind == "ewma" else "monthly",
            "half_life_days": vol.HALF_LIFE if kind == "ewma" else None,
            "min_history_months": vol.MIN_HISTORY_MONTHS if kind == "conditional" else None,
            "cost_bps": bt.COST_BPS,
            "returns": "excess over DFF",
        }
        store(engine, "vol_targeting", label, result, settings)


def pairs_trading(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None)
    groups = industries(engine)
    market = bt.run(studies.equal_weight(mask), returns).net
    for method in ("distance", "cointegration"):
        weights, counts = pairs.strategy_weights(method, prices, mask, groups)
        result_run = bt.run(weights, returns)
        strategy = result_run.net[result_run.net.index >= weights.index.min()]
        zero = pd.Series(0.0, index=strategy.index)  # Self-financing: the benchmark is no trade.
        result = judge(strategy, zero)
        result["windows"] = len(counts)
        result["average_pairs"] = float(sum(counts) / len(counts)) if counts else 0.0
        result["market_correlation"] = float(strategy.corr(market.reindex(strategy.index)))
        result["gross_annual_return"] = float(result_run.gross.reindex(strategy.index).mean() * 252)
        log = pairs.TRADE_LOG
        opened = [t for t in log if t["opens"]]
        result["pairs_chosen"] = len(log)
        result["share_of_pairs_that_traded"] = len(opened) / len(log) if log else None
        result["trades"] = sum(t["opens"] for t in log)
        result["average_days_open_per_trade"] = sum(t["days_open"] for t in log) / max(
            1, sum(t["opens"] for t in log)
        )
        net = strategy
        result["net_sharpe_by_period"] = {
            "2011-2015": summary(net[net.index.year <= 2015])["sharpe"],
            "2016-2020": summary(net[(net.index.year >= 2016) & (net.index.year <= 2020)])[
                "sharpe"
            ],
            "2021-2026": summary(net[net.index.year >= 2021])["sharpe"],
        }
        result["series"] = growth_series(strategy, zero)
        result["cost_drag_annual"] = float(
            (result_run.gross - result_run.net).reindex(strategy.index).mean() * 252
        )
        settings = {
            "formation_days": pairs.FORMATION,
            "trading_days": pairs.TRADING,
            "pairs": pairs.TOP,
            "open_at_sd": pairs.OPEN_AT,
            "wait_one_day": True,
            "same_industry": "SIC 2-digit",
            "cost_bps": bt.COST_BPS,
            "borrow_bps_a_year": bt.BORROW_BPS_A_YEAR,
            "returns": "committed capital",
        }
        store(engine, "pairs_trading", method, result, settings)


def value_at_risk(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None)
    portfolio = bt.run(studies.equal_weight(mask), returns).net
    portfolio = portfolio[portfolio.index > portfolio.index.min()]
    for method in ("historical", "normal", "ewma", "filtered historical", "gjr-garch t"):
        forecast = var.forecasts(portfolio, method)
        result = var.backtest(portfolio, forecast)
        if method == "gjr-garch t":
            result["fit_failures"] = var.garch_volatility(portfolio.dropna())[1]
        both = pd.concat([portfolio, forecast], axis=1, keys=["r", "var"]).dropna()
        hit = (both["r"] < -both["var"]).astype(int)
        monthly = pd.DataFrame({"hits": hit, "var": both["var"]}).resample("ME")
        result["series"] = {
            "months": [d.strftime("%Y-%m") for d in monthly.sum().index],
            "breaches": [int(v) for v in monthly.sum()["hits"]],
            "average_var": [round(float(v), 5) for v in monthly.mean()["var"]],
        }
        settings = {
            "level": var.LEVEL,
            "simulations": var.SIMULATIONS,
            "window_days": var.WINDOW,
            "ewma_decay": var.EWMA_DECAY,
            "garch_refit_days": var.GARCH_REFIT,
            "portfolio": "all tradeable stocks, equal weight",
        }
        store(engine, "value_at_risk", method, result, settings)


def panic_detector(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    returns = prices.pct_change(fill_method=None).where(mask)
    market = bt.run(studies.equal_weight(mask), prices.pct_change(fill_method=None)).net
    read = panic.readings(returns)
    result = panic.test(panic.shift_signal(read["absorption_ratio"]), market)
    result["average_correlation_median"] = float(read["average_correlation"].median())
    result["average_correlation_max"] = float(read["average_correlation"].max())
    result["average_correlation_max_date"] = read["average_correlation"].idxmax().date().isoformat()
    result["top_eigenvalue_share_median"] = float(read["top_eigenvalue_share"].median())
    signal = panic.shift_signal(read["absorption_ratio"])
    monthly = read.resample("ME").mean()
    result["series"] = {
        "months": [d.strftime("%Y-%m") for d in monthly.index],
        "average_correlation": [round(float(v), 4) for v in monthly["average_correlation"]],
        "absorption_ratio": [round(float(v), 4) for v in monthly["absorption_ratio"]],
        "warning_share": [round(float(v), 3) for v in signal.astype(float).resample("ME").mean()],
        "market": monthly_growth(market.reindex(read.index)),
    }
    settings = {
        "window_days": panic.WINDOW,
        "eigenvectors": "top fifth of stocks",
        "shift": "15-day mean >= 1 sd above 1-year mean",
        "ahead_days": panic.AHEAD,
    }
    store(engine, "panic_detector", "absorption ratio shift", result, settings)


CENTURY_VERSIONS = (
    ("variance", "variance-managed (Moreira-Muir)"),
    ("volatility", "volatility target"),
    ("conditional", "conditional (Bongaerts et al.)"),
    ("ewma", "daily EWMA (Harvey et al.)"),
)


def market_century(engine: Engine, prices: pd.DataFrame, mask: pd.DataFrame) -> None:
    """The same volatility rules and the same 50/200 trend rule, run on the whole US market's
    daily excess return since 1926 instead of 2010. Only the data is longer: code, settings,
    costs and the pass rule are unchanged, so a small edge has a fair chance to show."""
    history = market_history(engine)
    if len(history) < 252 * 50:
        raise SystemExit("Not verified: market history has not been loaded")
    excess = history["mkt_rf"]
    for kind, label in CENTURY_VERSIONS:
        strategy, held = vol.managed(excess, kind)
        baseline = excess.reindex(strategy.index)
        result = judge(strategy, baseline, by="alpha")
        result["average_exposure"] = float(held.mean())
        result["max_exposure"] = float(held.max())
        result["series"] = growth_series(strategy, baseline)
        settings = {
            "data": "US market excess return, French library, daily",
            "max_leverage": vol.MAX_LEVERAGE,
            "rebalance": "daily" if kind == "ewma" else "monthly",
            "cost_bps": bt.COST_BPS,
        }
        store(engine, "market_century", label, result, settings)
    level = (1 + excess + history["rf"]).cumprod()
    on = studies.trend_on(level)
    strategy = studies.trend_returns(on, excess)
    baseline = excess.reindex(strategy.index)
    result = judge(strategy, baseline)
    result["share_of_days_invested"] = float(on.shift(1).reindex(strategy.index).mean())
    result["series"] = growth_series(strategy, baseline)
    settings = {
        "data": "US market, French library, daily",
        "fast": 50,
        "slow": 200,
        "cost_bps": bt.COST_BPS,
    }
    store(engine, "market_century", "trend 50/200", result, settings)


STUDIES = {
    "ma_crossover": ma_crossover,
    "vol_targeting": vol_targeting,
    "pairs_trading": pairs_trading,
    "value_at_risk": value_at_risk,
    "panic_detector": panic_detector,
    "market_century": market_century,
}
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
