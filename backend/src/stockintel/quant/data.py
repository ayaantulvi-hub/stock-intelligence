"""Price panels for the quant studies, from stored daily bars.

Closes are back-adjusted for splits and dividends, so their changes are total returns. Only
stocks that were large at the time (from SEC public-float filings) are marked tradeable, which
reduces, but doesn't remove, survivorship bias.
"""

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from stockintel.backtest import eligibility, eligible_days
from stockintel.charts import adjust
from stockintel.localcache import daily_bars


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
