"""The Day trading page: TJR's rules on SPY and QQQ, live from Alpaca, and their tested record.

Minute bars are fetched when needed and not stored, to keep the database small. Only test
summaries are stored.

Run the test: python -m stockintel.day_trading test [months]
"""

import json
import sys
import time as clock
from datetime import UTC, datetime, time, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import Engine, text

from stockintel import intraday
from stockintel.config import get_settings
from stockintel.providers.alpaca import AlpacaProvider
from stockintel.providers.base import FeedError

SYMBOLS = ("SPY", "QQQ")
NY = "America/New_York"
MIN_TRADES = 30
MIN_T = 3.0
CACHE_SECONDS = 60
STALE_MINUTES = 10
RISK_SHARE = 0.01  # TJR: 1% to 3% a trade. The lowest is used.

_cache: dict = {}


def provider() -> AlpacaProvider:
    settings = get_settings()
    return AlpacaProvider(settings.alpaca_api_key_id, settings.alpaca_api_secret_key)


def summarise(values: np.ndarray) -> dict:
    n = len(values)
    if n == 0:
        return {"trades": 0, "mean_r": None, "win_rate": None, "t": None}
    sd = values.std(ddof=1) if n > 1 else 0.0
    return {
        "trades": n,
        "mean_r": float(values.mean()),
        "win_rate": float((values > 0).mean()),
        "t": float(values.mean() / (sd / np.sqrt(n))) if sd > 0 else None,
    }


def verdict(rows: list[dict]) -> dict:
    frame = pd.DataFrame(rows)
    result = summarise(frame["r"].to_numpy() if len(frame) else np.array([]))
    base = frame["random_r"].dropna().to_numpy() if len(frame) else np.array([])
    chance = summarise(base)
    edge = (
        result["trades"] >= MIN_TRADES
        and result["mean_r"] > 0
        and (result["t"] or 0) >= MIN_T
        and chance["mean_r"] is not None
        and result["mean_r"] > chance["mean_r"]
    )
    by = {}
    if len(frame):
        for column in ("confirmed_by", "level", "symbol"):
            by[column] = {str(k): summarise(g.to_numpy()) for k, g in frame.groupby(column)["r"]}
        years = pd.to_datetime(frame["entered"], utc=True).dt.year
        by["year"] = {str(k): summarise(g.to_numpy()) for k, g in frame.groupby(years)["r"]}
    return {
        **result,
        "chance": chance,
        "by": by,
        "verdict": "Edge shown in test" if edge else "No reliable edge",
    }


def run_test(engine: Engine, source: AlpacaProvider, months: int, now: datetime) -> dict:
    """Fetch history a month at a time, test the rules, and store only the summary."""
    end = now.astimezone(UTC)
    start = (pd.Timestamp(end).tz_convert(None) - pd.DateOffset(months=months)).replace(day=1)
    parts: dict[str, list] = {s: [] for s in SYMBOLS}
    provenance = None
    for first in pd.date_range(start, end.replace(tzinfo=None), freq="MS"):
        last = min(first + pd.DateOffset(months=1), pd.Timestamp(end).tz_convert(None))
        frames, provenance = source.minute_bars(
            SYMBOLS, first.tz_localize(UTC).to_pydatetime(), last.tz_localize(UTC).to_pydatetime()
        )
        for symbol, frame in frames.items():
            parts[symbol].append(frame)
    frames = {s: pd.concat(p, ignore_index=True) for s, p in parts.items() if p}
    if any(frames.get(s) is None or frames[s].empty for s in SYMBOLS):
        raise FeedError("Alpaca bars: no minute bars returned for SPY or QQQ")
    rows = intraday.backtest(frames)
    result = verdict(rows)
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO day_trade_tests (source, source_url, data_from, data_to, trades,
                     mean_r, win_rate, t_stat, baseline_mean_r, verdict, detail)
                   VALUES (:source, :url, :start, :end, :trades, :mean_r, :win_rate, :t,
                     :base, :verdict, CAST(:detail AS jsonb))"""
            ),
            {
                "source": provenance.source_name,
                "url": provenance.source_url,
                "start": min(f["time"].min() for f in frames.values()).date(),
                "end": max(f["time"].max() for f in frames.values()).date(),
                "trades": result["trades"],
                "mean_r": result["mean_r"],
                "win_rate": result["win_rate"],
                "t": result["t"],
                "base": result["chance"]["mean_r"],
                "verdict": result["verdict"],
                "detail": json.dumps(result["by"]),
            },
        )
    return result


def latest_test(engine: Engine) -> dict | None:
    query = """SELECT run_at, source, data_from, data_to, trades, mean_r, win_rate, t_stat,
                 baseline_mean_r, verdict, detail FROM day_trade_tests ORDER BY id DESC LIMIT 1"""
    with engine.connect() as conn:
        row = conn.execute(text(query)).first()
    return None if row is None else dict(row._mapping)


def window_times(day) -> dict:
    """The trading window for a New York date, in UTC, so the page shows local times."""
    start = pd.Timestamp.combine(day, intraday.WINDOW[0]).tz_localize(NY)
    end = pd.Timestamp.combine(day, intraday.WINDOW[1]).tz_localize(NY)
    return {"start": start.tz_convert(UTC).isoformat(), "end": end.tz_convert(UTC).isoformat()}


def plan_for(trade: intraday.Trade) -> dict:
    risk = abs(trade.entry - trade.stop)
    return {
        "ticker": trade.ticker,
        "side": trade.side,
        "level": trade.level,
        "confirmed_by": trade.confirmed_by,
        "entered_at": trade.entry_time.tz_convert(UTC).isoformat(),
        "entry": trade.entry,
        "stop": trade.stop,
        "target": trade.target,
        "reward_to_risk": abs(trade.target - trade.entry) / risk if risk else None,
        "result": trade.result,
        "exit": trade.exit,
        "r": trade.r,
    }


def today(engine: Engine, source=None, now: datetime | None = None) -> dict:
    """Levels, the current step and any setups for the latest session."""
    now = now or datetime.now(UTC)
    cached = _cache.get("today")
    if cached and clock.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    test = latest_test(engine)
    try:
        source = source or provider()
        frames, provenance = source.minute_bars(SYMBOLS, now - timedelta(days=8), now)
    except FeedError as exc:
        return {"error": str(exc), "test": test}
    if any(frames.get(s) is None or frames[s].empty for s in SYMBOLS):
        return {"error": "Alpaca returned no recent bars for SPY or QQQ.", "test": test}
    spy = frames["SPY"]
    day = spy["time"].iloc[-1].date()
    last_bar = spy["time"].iloc[-1]
    ny_now = pd.Timestamp(now).tz_convert(NY)
    open_now = ny_now.date() == day and time(9, 30) <= ny_now.time() < time(16)
    stale = open_now and (ny_now - last_bar) > pd.Timedelta(minutes=STALE_MINUTES)
    stocks = []
    for symbol, other in intraday.PAIR.items():
        mine, theirs = frames[symbol], frames[other]
        recent = mine[mine["time"].dt.date <= day]
        levels = intraday.key_levels(recent, day)
        state: dict = {}
        trades = (
            []
            if stale
            else intraday.scan_day(
                symbol,
                mine[mine["time"].dt.date == day],
                theirs[theirs["time"].dt.date == day],
                levels,
                live=ny_now.date() == day and ny_now.time() < intraday.LAST_EXIT,
                state=state,
            )
        )
        stocks.append(
            {
                "ticker": symbol,
                "price": float(mine["close"].iloc[-1]),
                "levels": sorted(
                    ({"name": k, "price": v} for k, v in levels.items()),
                    key=lambda x: -x["price"],
                ),
                "step": state,
                "setups": [plan_for(t) for t in trades],
            }
        )
    result = {
        "session": day.isoformat(),
        "window": window_times(day),
        "next_window": window_times(next_weekday(ny_now)),
        "market_open": open_now,
        "stale": stale,
        "last_bar": last_bar.tz_convert(UTC).isoformat(),
        "source": provenance.source_name,
        "source_url": provenance.source_url,
        "retrieved_at": provenance.retrieved_at.isoformat(),
        "risk_share": RISK_SHARE,
        "stocks": stocks,
        "test": test,
    }
    _cache["today"] = (clock.monotonic(), result)
    return result


def next_weekday(ny_now: pd.Timestamp):
    """The next weekday whose window hasn't ended. Holidays aren't skipped here."""
    day = ny_now.date()
    if ny_now.time() >= intraday.WINDOW[1]:
        day += timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


if __name__ == "__main__":
    if sys.argv[1:2] == ["test"]:
        from stockintel.db import get_engine

        months = int(sys.argv[2]) if len(sys.argv) > 2 else 36
        output = run_test(get_engine(), provider(), months, datetime.now(UTC))
        print(json.dumps({k: v for k, v in output.items() if k != "by"}, indent=2))
    else:
        sys.exit(__doc__)
