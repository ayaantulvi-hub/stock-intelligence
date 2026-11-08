"""Cross-check prices from different sources. A disagreement is stored with both values and
shown, never averaged away, because blending hides which source is wrong.

Checks, once a day:
1. Each holding and the 20 largest stocks: Tiingo's close against Alpaca's IEX daily close.
   IEX's close is its last trade, so small gaps are normal. Over 1% is flagged.
2. The S&P 500 (FRED) against SPY, and the Dow (FRED) against DIA (Alpaca, with dividends
   added back): the same day's percentage change. A gap over 0.3 points is flagged.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
from sqlalchemy import Engine, text

from stockintel.providers.base import FeedError

PRICE_GAP = 0.01
INDEX_GAP = 0.3  # Percentage points.
LARGEST = 20
PAIRS = {"SP500": ("SPY", "S&P 500"), "DJIA": ("DIA", "Dow Jones")}


def flag(conn, ticker, day, detail) -> None:
    conn.execute(
        text(
            """INSERT INTO validation_issues (feed, kind, ticker, market_date, detail)
               VALUES ('cross-check', 'conflict', :t, :d, :detail)"""
        ),
        {"t": ticker, "d": day, "detail": detail},
    )


def stock_closes(engine: Engine) -> dict:
    query = """SELECT s.ticker, b.market_date, b.close FROM securities s
               JOIN LATERAL (SELECT market_date, close FROM price_bars WHERE security_id = s.id
                 ORDER BY market_date DESC, id DESC LIMIT 1) b ON true
               WHERE s.universe_rank <= :n OR s.id IN (SELECT security_id FROM positions)"""
    with engine.connect() as conn:
        return {
            r.ticker: (r.market_date, r.close) for r in conn.execute(text(query), {"n": LARGEST})
        }


def index_changes(engine: Engine) -> dict:
    query = """SELECT DISTINCT ON (series_id, observation_date) series_id, observation_date, value
               FROM economic_observations WHERE series_id IN ('SP500', 'DJIA')
                 AND observation_date >= :since AND value IS NOT NULL
               ORDER BY series_id, observation_date, realtime_start DESC"""
    since = datetime.now(UTC).date() - timedelta(days=20)
    with engine.connect() as conn:
        rows = pd.DataFrame([r._mapping for r in conn.execute(text(query), {"since": since})])
    if rows.empty:
        return {}
    wide = rows.pivot(index="observation_date", columns="series_id", values="value").sort_index()
    return {series: wide[series].dropna().pct_change().dropna() * 100 for series in wide}


def run(engine: Engine, source, now: datetime | None = None) -> dict:
    now = now or datetime.now(UTC)
    closes = stock_closes(engine)
    start = now - timedelta(days=20)
    checked = flagged = 0
    symbols = {t.replace("-", "."): t for t in closes} | {v[0]: v[0] for v in PAIRS.values()}
    try:
        bars, _ = source.minute_bars(tuple(symbols), start, now, "1Day")
        adjusted, _ = source.minute_bars(
            tuple(v[0] for v in PAIRS.values()), start, now, "1Day", adjustment="all"
        )
    except FeedError as exc:
        return {"error": str(exc)}
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM validation_issues WHERE feed = 'cross-check' AND detected_at >= :d"),
            {"d": now - timedelta(hours=20)},
        )
        for symbol, ticker in symbols.items():
            if ticker not in closes or symbol not in bars:
                continue
            day, close = closes[ticker]
            frame = bars[symbol]
            same = frame[frame["time"].dt.date == day]
            if same.empty:
                continue
            other = float(same["close"].iloc[-1])
            checked += 1
            if abs(other / close - 1) > PRICE_GAP:
                flagged += 1
                flag(
                    conn,
                    ticker,
                    day,
                    f"Closing price disagrees: Tiingo {close:.2f}, Alpaca (IEX) {other:.2f}, "
                    f"a {abs(other / close - 1):.1%} gap. Check the chart before acting.",
                )
        for series, change in index_changes(engine).items():
            fund, name = PAIRS[series]
            if fund not in adjusted or change.empty:
                continue
            frame = adjusted[fund].set_index(adjusted[fund]["time"].dt.date)["close"]
            fund_change = frame.pct_change().dropna() * 100
            common = sorted(set(change.index) & set(fund_change.index))
            if not common:
                continue
            day = common[-1]
            a, b = float(change[day]), float(fund_change[day])
            checked += 1
            if abs(a - b) > INDEX_GAP:
                flagged += 1
                flag(
                    conn,
                    fund,
                    day,
                    f"{name} moved {a:+.2f}% (FRED) but {fund} moved {b:+.2f}% (Alpaca). "
                    "They track the same index, so one figure may be wrong or late.",
                )
    return {"checked": checked, "flagged": flagged}


if __name__ == "__main__":
    import json

    from stockintel.day_trading import provider
    from stockintel.db import get_engine
    from stockintel.ingest import Run

    engine = get_engine()
    record = Run(engine, "cross-check")
    try:
        result = run(engine, provider())
    except FeedError as exc:
        result = {"error": str(exc)}
    print(json.dumps(result))
    if "error" in result:
        record.finish(result["error"])
    else:
        record.attempted = record.ok = result["checked"]
        record.added = result["flagged"]
        record.finish()
