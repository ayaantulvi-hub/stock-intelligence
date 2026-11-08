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

from stockintel import intraday, market, news_watch, orb, timemachine
from stockintel.config import get_settings
from stockintel.providers.alpaca import AlpacaProvider
from stockintel.providers.base import FeedError

SYMBOLS = ("SPY", "QQQ")
NY = "America/New_York"
MIN_TRADES = 30
MIN_T = 3.0
CACHE_SECONDS = 60
STALE_MINUTES = 10
from stockintel.plan import MAX_RISK_SHARE as RISK_SHARE  # One limit everywhere: 1.5%.

ORB_TEST_STOCKS = 30  # The opening-range test uses the largest stocks in the universe.
ORB_SHOWN = 10
ORB_REPLAYED = 5
CHUNK = 100  # Symbols a request.

_cache: dict = {}


def provider() -> AlpacaProvider:
    settings = get_settings()
    return AlpacaProvider(settings.alpaca_api_key_id, settings.alpaca_api_secret_key)


def event_days(engine: Engine) -> dict:
    """Dates of the Fed's rate decisions and the big 8:30am releases, by date."""
    query = """SELECT release_date AS day, name FROM economic_releases
               UNION ALL SELECT decision_date, 'Fed rate decision' FROM fed_meetings"""
    found: dict = {}
    with engine.connect() as conn:
        for row in conn.execute(text(query)):
            found.setdefault(row.day, []).append(row.name)
    return found


def earnings_days(engine: Engine) -> dict[str, set]:
    """Days each stock announced results (8-K item 2.02), and the day after, for late filers."""
    query = """SELECT s.ticker, e.filing_date FROM filing_events e
               JOIN securities s ON s.id = e.security_id WHERE e.items LIKE '%2.02%'"""
    found: dict[str, set] = {}
    with engine.connect() as conn:
        for row in conn.execute(text(query)):
            days = found.setdefault(row.ticker, set())
            days.add(row.filing_date)
            days.add(row.filing_date + timedelta(days=1))
    return found


def label_days(rows: list[dict], events: dict, earnings: dict[str, set]) -> list[dict]:
    for row in rows:
        day = pd.Timestamp(row["entered"]).tz_convert(NY).date()
        row["event_day"] = "Release or Fed day" if day in events else "Ordinary day"
        if row["symbol"] in earnings:
            row["results_day"] = "Results day" if day in earnings[row["symbol"]] else "No results"
    return rows


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
        for column in ("confirmed_by", "level", "symbol", "event_day", "results_day"):
            if column not in frame:
                continue
            by[column] = {str(k): summarise(g.to_numpy()) for k, g in frame.groupby(column)["r"]}
        years = pd.to_datetime(frame["entered"], utc=True).dt.year
        by["year"] = {str(k): summarise(g.to_numpy()) for k, g in frame.groupby(years)["r"]}
    return {
        **result,
        "chance": chance,
        "by": by,
        "verdict": "Edge shown in test" if edge else "No reliable edge",
    }


def alpaca_symbol(ticker: str) -> str:
    return ticker.replace("-", ".")


def universe(engine: Engine, limit: int | None = None) -> list[str]:
    query = "SELECT ticker FROM securities ORDER BY universe_rank" + (" LIMIT :n" if limit else "")
    with engine.connect() as conn:
        return list(conn.execute(text(query), {"n": limit}).scalars())


def fetch(source, tickers, start, end, timeframe):
    """Bars for many tickers, a chunk at a time, keyed by our ticker spelling."""
    frames, provenance = {}, None
    for i in range(0, len(tickers), CHUNK):
        chunk = tickers[i : i + CHUNK]
        names = {alpaca_symbol(t): t for t in chunk}
        got, provenance = source.minute_bars(tuple(names), start, end, timeframe)
        for symbol, frame in got.items():
            if symbol in names and not frame.empty:
                frames[names[symbol]] = frame
    return frames, provenance


def run_test(
    engine: Engine, source: AlpacaProvider, months: int, now: datetime, strategy: str = "TJR"
) -> dict:
    """Fetch history a month at a time, test the rules, and store only the summary."""
    end = now.astimezone(UTC)
    if strategy == "ORB":
        return _run_orb_test(engine, source, months, end)
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
    rows = label_days(intraday.backtest(frames), event_days(engine), {})
    result = verdict(rows)
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO day_trade_tests (strategy, source, source_url, data_from,
                     data_to, trades, mean_r, win_rate, t_stat, baseline_mean_r, verdict, detail)
                   VALUES (:strategy, :source, :url, :start, :end, :trades, :mean_r, :win_rate,
                     :t, :base, :verdict, CAST(:detail AS jsonb))"""
            ),
            {
                "strategy": strategy,
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


def _run_orb_test(engine: Engine, source, months: int, end: datetime) -> dict:
    tickers = universe(engine, ORB_TEST_STOCKS)
    start = (pd.Timestamp(end).tz_convert(None) - pd.DateOffset(months=months)).replace(day=1)
    rows, provenance, first, last = [], None, None, None
    for month in pd.date_range(start, end.replace(tzinfo=None), freq="MS"):
        stop = min(month + pd.DateOffset(months=1), pd.Timestamp(end).tz_convert(None))
        frames, provenance = fetch(
            source,
            tickers,
            month.tz_localize(UTC).to_pydatetime(),
            stop.tz_localize(UTC).to_pydatetime(),
            "5Min",
        )
        if frames:
            low = min(f["time"].min() for f in frames.values()).date()
            high = max(f["time"].max() for f in frames.values()).date()
            first, last = min(first or low, low), max(last or high, high)
        rows += orb.backtest(frames)
    rows = label_days(rows, event_days(engine), earnings_days(engine))
    if provenance is None or first is None:
        raise FeedError("Alpaca bars: no 5-minute bars returned for the opening-range test")
    result = verdict(rows)
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO day_trade_tests (strategy, source, source_url, data_from,
                     data_to, trades, mean_r, win_rate, t_stat, baseline_mean_r, verdict, detail)
                   VALUES ('ORB', :source, :url, :start, :end, :trades, :mean_r, :win_rate,
                     :t, :base, :verdict, CAST(:detail AS jsonb))"""
            ),
            {
                "source": provenance.source_name,
                "url": provenance.source_url,
                "start": first,
                "end": last,
                "trades": result["trades"],
                "mean_r": result["mean_r"],
                "win_rate": result["win_rate"],
                "t": result["t"],
                "base": result["chance"]["mean_r"],
                "verdict": result["verdict"],
                "detail": json.dumps({**result["by"], "stocks": tickers}),
            },
        )
    return result


def latest_test(engine: Engine, strategy: str = "TJR") -> dict | None:
    query = """SELECT run_at, strategy, source, data_from, data_to, trades, mean_r, win_rate,
                 t_stat, baseline_mean_r, verdict, detail FROM day_trade_tests
               WHERE strategy = :s ORDER BY id DESC LIMIT 1"""
    with engine.connect() as conn:
        row = conn.execute(text(query), {"s": strategy}).first()
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
    events = event_days(engine).get(day, [])
    result = {
        "events": events,
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
    try:
        add_replays(result, source, frames, day, now)
        result["orb"] = scan_orb(engine, source, day, now)
    except FeedError as exc:
        result["orb"] = {"error": str(exc)}
    add_cautions(engine, result, day, events)
    result["orb_test"] = latest_test(engine, "ORB")
    _cache["today"] = (clock.monotonic(), result)
    return result


def add_cautions(engine: Engine, result: dict, day, events: list[str]) -> None:
    """Reasons to be careful with each setup: a release day, results day or bad news."""
    warnings = news_watch.stock_warnings(engine, day)
    market_wide = news_watch.warnings(engine, day).get("Whole market")
    results = earnings_days(engine)
    setups = [s for stock in result["stocks"] for s in stock["setups"]]
    setups += result.get("orb", {}).get("setups", []) or []
    for setup in setups:
        notes = [f"{name} today: prices can jump at the release" for name in events]
        if day in results.get(setup["ticker"], set()):
            notes.append("Results announced today or last night: moves can be much bigger")
        if setup["ticker"] in warnings:
            notes.append(f"News warning: {warnings[setup['ticker']]}")
        if market_wide and setup["ticker"] in ("SPY", "QQQ"):
            notes.append(f"News warning for the whole market: {market_wide['title']}")
        setup["cautions"] = notes


def completed(frame: pd.DataFrame, now: datetime, minutes: int) -> pd.DataFrame:
    """Drop the bar still forming, so nothing uses a price that isn't final."""
    ends = frame["time"] + pd.Timedelta(minutes=minutes)
    return frame[ends <= pd.Timestamp(now).tz_convert(NY)]


def history_bars(source, tickers, day, now) -> dict[str, pd.DataFrame]:
    start = pd.Timestamp(day).tz_localize(NY) - pd.Timedelta(days=95)
    frames, _ = fetch(source, list(tickers), start.to_pydatetime(), now, "5Min")
    return {t: completed(f, now, 5) for t, f in frames.items()}


def add_replays(result: dict, source, frames, day, now) -> None:
    """Time Machine replays for each TJR setup still open."""
    wanted = {s["ticker"] for stock in result["stocks"] for s in stock["setups"]}
    if not wanted:
        return
    bars = history_bars(source, wanted, day, now)
    for stock in result["stocks"]:
        for plan in stock["setups"]:
            if stock["ticker"] in bars:
                plan["replay"] = timemachine.run(
                    bars[stock["ticker"]],
                    day,
                    pd.Timestamp(plan["entered_at"]).tz_convert(NY),
                    plan["entry"],
                    plan["stop"],
                    plan["target"],
                    plan["side"] == "long",
                    intraday.LAST_EXIT,
                )


def scan_orb(engine: Engine, source, day, now) -> dict:
    """Opening-range breakouts across the universe so far today, most traded first."""
    tickers = universe(engine)
    open_at = pd.Timestamp.combine(day, time(9, 30)).tz_localize(NY)
    end = min(pd.Timestamp(now).tz_convert(NY), open_at + pd.Timedelta(hours=6, minutes=30))
    if end <= open_at:
        return {"scanned": 0, "found": 0, "setups": []}
    frames, provenance = fetch(
        source, tickers, open_at.to_pydatetime(), end.to_pydatetime(), "5Min"
    )
    found = []
    for ticker, frame in frames.items():
        bars = completed(frame[frame["time"] >= open_at], now, 5)
        rows = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
        if len(rows) <= orb.RANGE_BARS or rows[-1, 3] < orb.MIN_PRICE:
            continue
        # A missing 5-minute bar means a halt or no trades, so the range can't be trusted.
        expected = timemachine.bar_index(bars["time"].iloc[-1]) + 1
        if len(rows) != expected:
            continue
        plan = orb.setup(rows)
        if plan is None:
            continue
        traded = float((bars["close"] * bars["volume"]).sum())
        found.append(
            {
                "ticker": ticker,
                "side": "long" if plan["long"] else "short",
                "entered_at": (bars["time"].iloc[plan["bar"]] + pd.Timedelta(minutes=5))
                .tz_convert(UTC)
                .isoformat(),
                "entry": plan["entry"],
                "stop": plan["stop"],
                "target": plan["target"],
                "range_high": plan["range_high"],
                "range_low": plan["range_low"],
                "price": float(rows[-1, 3]),
                "traded": traded,
                "plan": plan,
            }
        )
    found.sort(key=lambda h: -h["traded"])
    shown = found[:ORB_SHOWN]
    replay = [h["ticker"] for h in shown[:ORB_REPLAYED]]
    bars = history_bars(source, replay, day, now) if replay else {}
    flat_last = timemachine.bar_index(pd.Timestamp.combine(day, orb.FLAT_BY)) - 1
    for hit in shown:
        plan = hit.pop("plan")
        if hit["ticker"] in bars:
            hit["replay"] = timemachine.run(
                bars[hit["ticker"]],
                day,
                pd.Timestamp(hit["entered_at"]).tz_convert(NY),
                plan["entry"],
                plan["stop"],
                plan["target"],
                plan["long"],
                orb.FLAT_BY,
                history=lambda days, last: orb.history(days, flat_last),
            )
    for hit in found[ORB_SHOWN:]:
        hit.pop("plan")
    return {
        "scanned": len(frames),
        "found": len(found),
        "setups": shown,
        "source": provenance.source_name if provenance else None,
    }


def next_weekday(ny_now: pd.Timestamp):
    """The next trading day whose window hasn't ended, skipping weekends and NYSE holidays."""
    day = ny_now.date()
    if ny_now.time() >= intraday.WINDOW[1]:
        day += timedelta(days=1)
    while not market.is_session(day):
        day += timedelta(days=1)
    return day


if __name__ == "__main__":
    if sys.argv[1:2] == ["test"]:
        from stockintel.db import get_engine

        months = int(sys.argv[2]) if len(sys.argv) > 2 else 36
        strategy = sys.argv[3] if len(sys.argv) > 3 else "TJR"
        output = run_test(get_engine(), provider(), months, datetime.now(UTC), strategy)
        print(strategy, json.dumps({k: v for k, v in output.items() if k != "by"}, indent=2))
    else:
        sys.exit(__doc__)
