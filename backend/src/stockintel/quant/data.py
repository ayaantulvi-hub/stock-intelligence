"""Price panels for the quant studies, from stored daily bars.

Closes are back-adjusted for splits and dividends, so their changes are total returns. Only
stocks that were large at the time (from SEC public-float filings) are marked tradeable, which
reduces, but doesn't remove, survivorship bias.
"""

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from stockintel.localcache import daily_bars
from stockintel.prices import adjust, eligibility, eligible_days


def panels(engine: Engine, min_days: int = 500) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(adjusted closes, tradeable mask), each dates x tickers, oldest first."""
    with engine.connect() as conn:
        tickers = dict(conn.execute(text("SELECT id, ticker FROM securities")).all())
        ciks = dict(conn.execute(text("SELECT id, cik FROM securities")).all())
    closes = {}
    for security_id, bars in daily_bars(engine).items():
        if len(bars) < min_days or security_id not in tickers:
            continue
        adjusted = adjust(bars)
        closes[tickers[security_id]] = pd.Series(
            adjusted["close"].to_numpy(), index=pd.to_datetime(adjusted["market_date"])
        )
    prices = pd.DataFrame(closes).sort_index()
    eligible_years = eligibility(engine)
    mask = pd.DataFrame(False, index=prices.index, columns=prices.columns)
    by_ticker = {tickers[s]: ciks.get(s) for s in tickers}
    dates = pd.Series(prices.index)
    for ticker in prices.columns:
        allowed = eligible_years.get(by_ticker.get(ticker), set())
        # A size reported for a year is only known from the following April (as in backtest.py).
        mask[ticker] = eligible_days(dates, allowed) & prices[ticker].notna().to_numpy()
    return prices, mask


def risk_free(engine: Engine, index: pd.DatetimeIndex) -> pd.Series:
    """Daily risk-free return from the effective Fed funds rate (FRED DFF), known the next day.
    Missing days carry the last known rate forward; a gap before the first reading stays NaN."""
    query = """SELECT DISTINCT ON (observation_date) observation_date, value
               FROM economic_observations WHERE series_id = 'DFF' AND value IS NOT NULL
               ORDER BY observation_date, realtime_start DESC"""
    with engine.connect() as conn:
        rows = conn.execute(text(query)).all()
    if not rows:
        return pd.Series(float("nan"), index=index)
    rate = pd.Series([r[1] for r in rows], index=pd.to_datetime([r[0] for r in rows]))
    rate = rate.shift(1, freq="D")  # Published the next day.
    daily = rate.reindex(rate.index.union(index)).ffill().reindex(index)
    return daily / 100 / 252


def industries(engine: Engine) -> dict[str, str]:
    """Ticker -> first two digits of its SEC industry code, for stocks that have one."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT ticker, sic FROM securities WHERE sic IS NOT NULL")).all()
    return {ticker: str(sic).zfill(4)[:2] for ticker, sic in rows}
