"""Factor register and calculations.

Papers decide what is included. They do not set the weights: the model learns those from
past data, and walk-forward testing decides whether the result is trusted. Published
effects are not used directly, because McLean and Pontiff (2016) found returns 58% lower
after publication and Hou, Xue and Zhang (2020) found most anomalies fail to replicate.

`effect` holds only a figure read from the paper itself. None means not yet read.
"""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Factor:
    id: str
    name: str
    group: str
    source: str
    status: str  # "live" or what it still needs.
    effect: str | None = None
    url: str | None = None


LIVE = "live"
NEEDS_FUNDAMENTALS = "Needs SEC company facts (free, Milestone 6)"
NEEDS_FORM_4 = "Needs SEC Form 4 parsing (free)"
NEEDS_OPTIONS = "Needs a paid options feed"
NEEDS_NEWS = "Needs a news feed"
NEEDS_CALENDAR = "Needs the official meeting calendar (free)"

REGISTER = [
    Factor(
        "mom_12_1",
        "12-month momentum, skipping the last month",
        "Momentum",
        "Jegadeesh & Titman (1993), Journal of Finance",
        LIVE,
        url="https://ideas.repec.org/a/bla/jfinan/v48y1993i1p65-91.html",
    ),
    Factor(
        "mom_6_1",
        "6-month momentum, skipping the last month",
        "Momentum",
        "Jegadeesh & Titman (1993), Journal of Finance",
        LIVE,
        url="https://ideas.repec.org/a/bla/jfinan/v48y1993i1p65-91.html",
    ),
    Factor(
        "reversal_1m", "1-month reversal", "Momentum", "Jegadeesh (1990), Journal of Finance", LIVE
    ),
    Factor(
        "reversal_5d",
        "1-week reversal",
        "Momentum",
        "Lehmann (1990), Quarterly Journal of Economics",
        LIVE,
    ),
    Factor(
        "high_52w",
        "Distance from 52-week high",
        "Momentum",
        "George & Hwang (2004), Journal of Finance",
        LIVE,
    ),
    Factor(
        "vol_60",
        "60-day volatility",
        "Risk",
        "Ang, Hodrick, Xing & Zhang (2006), Journal of Finance",
        LIVE,
    ),
    Factor(
        "vol_20",
        "20-day volatility",
        "Risk",
        "Ang, Hodrick, Xing & Zhang (2006), Journal of Finance",
        LIVE,
    ),
    Factor(
        "beta",
        "Sensitivity to the market",
        "Risk",
        "Frazzini & Pedersen (2014), Journal of Financial Economics",
        LIVE,
    ),
    Factor(
        "max_ret",
        "Largest daily gain, last month",
        "Risk",
        "Bali, Cakici & Whitelaw (2011), Journal of Financial Economics",
        LIVE,
    ),
    Factor(
        "illiquidity",
        "Price impact of trading",
        "Liquidity",
        "Amihud (2002), Journal of Financial Markets",
        LIVE,
    ),
    Factor(
        "dollar_volume",
        "Average value traded",
        "Liquidity",
        "Gu, Kelly & Xiu (2020), Review of Financial Studies",
        LIVE,
        "Momentum, liquidity and volatility were the leading predictors",
        "https://nber.org/papers/w25398",
    ),
    Factor(
        "rsi", "RSI", "Technical", "Wilder (1978), New Concepts in Technical Trading Systems", LIVE
    ),
    Factor("macd_hist", "MACD histogram", "Technical", "Appel, MACD indicator", LIVE),
    Factor(
        "above_200",
        "Price against 200-day average",
        "Technical",
        "Brock, Lakonishok & LeBaron (1992), Journal of Finance",
        LIVE,
    ),
    Factor(
        "chart_pattern",
        "Recent chart pattern",
        "Technical",
        "Lo, Mamaysky & Wang (2000), Journal of Finance",
        LIVE,
        "Several technical indicators gave incremental information, 1962 to 1996",
        "https://www.nber.org/papers/w7613",
    ),
    Factor(
        "yield_slope",
        "10-year minus 2-year Treasury yield",
        "Economy",
        "Estrella & Mishkin (1998), Review of Economics and Statistics",
        LIVE,
    ),
    Factor("market_20d", "Whole-market 20-day return", "Economy", "Market-wide control", LIVE),
    Factor(
        "revenue_growth",
        "Latest quarter's sales against a year before",
        "Growth",
        "Quarterly SEC filings",
        LIVE,
    ),
    Factor(
        "sector_value",
        "Value compared within its industry",
        "Sector",
        "Compared with its own industry group",
        LIVE,
    ),
    Factor(
        "sector_profit",
        "Profitability compared within its industry",
        "Sector",
        "Compared with its own industry group",
        LIVE,
    ),
    Factor(
        "sector_momentum",
        "12-month momentum compared within its industry",
        "Sector",
        "Compared with its own industry group",
        LIVE,
    ),
    Factor("vix", "Market fear gauge (VIX)", "Economy", "Cboe VIX, through FRED", LIVE),
    Factor(
        "credit_spread", "Corporate borrowing premium", "Economy", "Moody's, through FRED", LIVE
    ),
    Factor("oil_20d", "Oil price, 20-day change", "Economy", "EIA, through FRED", LIVE),
    Factor("inflation_expected", "Expected inflation", "Economy", "Through FRED", LIVE),
    Factor(
        "jobless_claims",
        "Jobless claims, 4-week change",
        "Economy",
        "US Labor Department, through FRED",
        LIVE,
    ),
    Factor(
        "value",
        "Book-to-market value",
        "Value",
        "Fama & French (1992), Journal of Finance",
        LIVE,
    ),
    Factor(
        "size",
        "Company size",
        "Value",
        "Banz (1981), Journal of Financial Economics",
        LIVE,
    ),
    Factor(
        "profitability",
        "Gross profitability",
        "Quality",
        "Novy-Marx (2013), Journal of Financial Economics",
        LIVE,
    ),
    Factor(
        "investment",
        "Asset growth",
        "Quality",
        "Fama & French (2015), Journal of Financial Economics",
        LIVE,
    ),
    Factor(
        "accruals",
        "Accounting accruals",
        "Quality",
        "Sloan (1996), The Accounting Review",
        LIVE,
    ),
    Factor(
        "f_score",
        "Financial health score",
        "Quality",
        "Piotroski (2000), Journal of Accounting Research",
        NEEDS_FUNDAMENTALS,
    ),
    Factor(
        "issuance",
        "Net share issuance",
        "Quality",
        "Pontiff & Woodgate (2008), Journal of Finance",
        LIVE,
    ),
    Factor(
        "earnings_drift",
        "Drift after earnings surprises",
        "Events",
        "Bernard & Thomas (1989), Journal of Accounting Research",
        LIVE,
    ),
    Factor(
        "insider",
        "Opportunistic insider trades",
        "Events",
        "Cohen, Malloy & Pomorski (2012), Journal of Finance",
        LIVE,
        "Long-short 0.82% a month, value-weighted, before publication decay. This app uses a simpler measure",
        "https://www.nber.org/papers/w16454.pdf",
    ),
    Factor(
        "fscore",
        "Business health score",
        "Quality",
        "Piotroski (2000), Journal of Accounting Research",
        LIVE,
        "Nine accounting tests split cheap stocks into winners and losers",
        "https://www.jstor.org/stable/2672906",
    ),
    Factor(
        "insider_cluster",
        "Several insiders buying together",
        "Events",
        "Alldredge & Blank (2019), Journal of Financial Research",
        LIVE,
        "Trades clustered among colleagues carried more information than lone trades",
        "https://ideas.repec.org/a/bla/jfnres/v42y2019i2p331-360.html",
    ),
    Factor(
        "fomc",
        "Drift before Fed announcements",
        "Events",
        "Lucca & Moench (2015), Journal of Finance",
        LIVE,
        "S&P 500 rose 49 basis points on average in the 24 hours before, 1994 to 2011",
        "https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr512.pdf",
    ),
    Factor(
        "curve_3m",
        "Yield curve, 10-year minus 3-month",
        "Economy",
        "Estrella & Mishkin (1998), Review of Economics and Statistics",
        LIVE,
        "An inverted curve has often come before US recessions",
        "https://fred.stlouisfed.org/series/T10Y3M",
    ),
    Factor(
        "fed_direction",
        "Direction of Fed interest rates",
        "Economy",
        "Bernanke & Kuttner (2005), Journal of Finance",
        LIVE,
        "Surprise rate cuts tended to lift stocks",
        "https://fred.stlouisfed.org/series/DFF",
    ),
    Factor(
        "policy_uncertainty",
        "Government policy uncertainty",
        "Government",
        "Baker, Bloom & Davis (2016), Quarterly Journal of Economics",
        LIVE,
        "A news-based measure of uncertainty over policy",
        "https://fred.stlouisfed.org/series/USEPUINDXD",
    ),
    Factor(
        "policy_actions",
        "Recent presidential actions",
        "Government",
        "Federal Register count, not a published effect",
        LIVE,
        "Executive orders and policy proclamations in the last 30 days",
        "https://www.federalregister.gov/presidential-documents",
    ),
    Factor(
        "election_window",
        "Close to a US federal election",
        "Government",
        "Santa-Clara & Valkanov (2003), Journal of Finance",
        LIVE,
    ),
    Factor(
        "midterm_year",
        "Midterm election year",
        "Government",
        "Santa-Clara & Valkanov (2003), Journal of Finance",
        LIVE,
    ),
    Factor(
        "rate_beta",
        "Sensitivity to interest rates",
        "Economy",
        "Sweeney & Warga (1986), Journal of Finance",
        LIVE,
    ),
    Factor(
        "policy_beta",
        "Sensitivity to policy uncertainty",
        "Government",
        "Brogaard & Detzel (2015), Management Science",
        LIVE,
    ),
    Factor("implied_move", "Options-implied move", "Options", "Options market", NEEDS_OPTIONS),
    Factor(
        "variance_premium",
        "Implied minus realised volatility",
        "Options",
        "Bollerslev, Tauchen & Zhou (2009), Review of Financial Studies",
        NEEDS_OPTIONS,
    ),
    Factor("news_sentiment", "News tone", "News", "Tetlock (2007), Journal of Finance", NEEDS_NEWS),
]
LIVE_IDS = [factor.id for factor in REGISTER if factor.status == LIVE]
MARKET_WIDE = {
    "yield_slope",
    "market_20d",
    "vix",
    "credit_spread",
    "oil_20d",
    "inflation_expected",
    "jobless_claims",
    "fomc",
    "curve_3m",
    "fed_direction",
    "policy_uncertainty",
    "policy_actions",
    "election_window",
    "midterm_year",
}
NAMES = {factor.id: factor.name for factor in REGISTER}


HIGH_MEANS = {
    "mom_12_1": "Rose more than most stocks over the past year",
    "mom_6_1": "Rose more than most stocks over the past 6 months",
    "reversal_1m": "Rose more than most stocks this month",
    "reversal_5d": "Rose more than most stocks this week",
    "high_52w": "Closer to its 52-week high than most stocks",
    "vol_60": "Swings more than most stocks",
    "vol_20": "Swung more than most stocks this month",
    "beta": "Moves more than most stocks when the market moves",
    "max_ret": "Had a bigger one-day jump than most stocks",
    "illiquidity": "Trades move its price more than most stocks",
    "dollar_volume": "More money trades in it than most stocks",
    "rsi": "Stronger recent buying than most stocks",
    "macd_hist": "Stronger short-term trend than most stocks",
    "above_200": "Further above its 200-day average than most stocks",
    "revenue_growth": "Sales grew faster than most stocks",
    "sector_value": "Cheaper than most stocks in its industry",
    "sector_profit": "More profitable than most stocks in its industry",
    "sector_momentum": "Rose more than most stocks in its industry",
    "chart_pattern": "Recently completed a bullish chart pattern",
    "value": "Priced cheaply against its accounting value, compared with most stocks",
    "size": "A larger company than most covered stocks",
    "profitability": "Earns more gross profit per dollar of assets than most stocks",
    "investment": "Grew its assets faster than most stocks",
    "accruals": "Profits are backed less by cash than at most stocks",
    "issuance": "Issued more new shares than most stocks",
    "earnings_drift": "Profit rose more than most stocks in a recent yearly report",
    "insider": "Insiders bought more on the open market than at most stocks",
    "fscore": "Passed more business health tests than most stocks",
    "rate_beta": "Has tended to rise more than most stocks when long-term rates rise",
    "policy_beta": "Has tended to rise more than most stocks when policy uncertainty rises",
    "insider_cluster": "More different insiders bought recently than at most stocks",
}


def register() -> list[dict]:
    return [{**asdict(factor), "high_means": HIGH_MEANS.get(factor.id)} for factor in REGISTER]


def stock_factors(frame: pd.DataFrame, market_returns: pd.Series | None = None) -> pd.DataFrame:
    """One row per candle, using only that candle and earlier ones."""
    from stockintel.charts import macd, pattern_score, rsi, sma

    close, volume = frame["close"], frame["volume"]
    daily = close.pct_change(fill_method=None)
    dollars = close * volume
    result = pd.DataFrame(index=frame.index)
    result["mom_12_1"] = close.shift(21) / close.shift(252) - 1
    result["mom_6_1"] = close.shift(21) / close.shift(126) - 1
    result["reversal_1m"] = close / close.shift(21) - 1
    result["reversal_5d"] = close / close.shift(5) - 1
    result["high_52w"] = close / close.rolling(252).max() - 1
    result["vol_60"] = daily.rolling(60).std()
    result["vol_20"] = daily.rolling(20).std()
    result["max_ret"] = daily.rolling(21).max()
    result["illiquidity"] = (daily.abs() / dollars.replace(0, np.nan)).rolling(21).mean()
    result["dollar_volume"] = np.log(dollars.rolling(21).mean().replace(0, np.nan))
    result["rsi"] = rsi(close)
    result["macd_hist"] = macd(close)["histogram"] / close
    result["above_200"] = close / sma(close, 200) - 1
    result["chart_pattern"] = pattern_score(frame)
    if market_returns is not None:
        market = pd.Series(market_returns.to_numpy(), index=frame.index)
        result["beta"] = daily.rolling(252).cov(market) / market.rolling(252).var()
    else:
        result["beta"] = np.nan
    return result
