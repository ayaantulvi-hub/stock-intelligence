# Decisions

Provider facts were read from provider pages on 3 November 2026. Recheck them
before integrating or paying, because prices and terms change.

## Version 1 scope (confirmed by the owner)

| Decision | Choice |
|---|---|
| Coverage | About 500 US large caps |
| Data budget | $0 to start |
| Audience | Owner only |
| Hosting | Online and private: GitHub private repository, Neon database, password-protected Render dashboard. Not yet set up or tested |

## Data sources

| Role | Source | Cost | Key | Notes |
|---|---|---|---|---|
| Daily prices | Tiingo Starter | $0 | Yes | 500 symbols a month, 50 requests an hour, 1,000 a day. Internal, personal use only |
| Filings, fundamentals | SEC EDGAR | $0 | No | 10 requests a second. User-Agent must name the project and a contact email |
| Economic data | FRED | $0 | Yes | Past versions available. Must show the FRED notice. Copyrighted series are personal use only unless the owner permits |

Upgrade paths: Tiingo Power at $30 a month, Massive Developer at $79 (15-minute
delay, 10 years), Massive Advanced at $199 (real-time, 20+ years).

Rejected for now:
- FMP: terms bar copying content without prior approval, and require telling FMP where data is stored.
- Twelve Data Basic: limited to non-display use, and this app displays data.
- Massive Basic: 2 years of history is too short for backtesting.
- Alpaca: market data needs an account, and UAE availability is unconfirmed.
- Yahoo: lowest-ranked source in the brief, with no licensed plan found for this use.

## Stack

As suggested in the brief, with one change: plain PostgreSQL 16 instead of TimescaleDB.

- Reason: about 500 stocks over 20 years of daily bars is around 2.5 million rows.
- Reason: TimescaleDB could not be installed or tested in the build workspace.
- Cost of reversing: low, since it is a PostgreSQL extension.
- If it is added: Community Edition is free to self-host. Apache 2 Edition lacks continuous aggregates.

## Indicator accuracy

| Check | Independent reference | Tolerance | Result |
|---|---|---|---|
| SMA, EMA, RSI, MACD | TA-Lib, on a fixed test series | 0.000001 | Pass, in `tests/test_charts.py` |
| Adjusted close | Tiingo `adjClose`, on real AAPL, NVDA, JPM, WMT and XOM | 0.25% | Worst 0.16% (XOM), about 4,234 bars each |

Run the second check with **Actions → Live access check**. It uses 5 Tiingo requests.

Signals show as Unproven until Milestone 4 gives them a tested record. Bullish or Bearish
needs at least 30 tested cases that beat the baseline.

## Backtesting

- Trades enter at the next open and pay 0.10% round-trip costs. That cost is an assumption.
- Each year counts only if earlier years alone had already shown an edge.
- An edge needs 30 tested cases, a higher average return than the baseline, and a win rate
  at least 3 standard errors above it. The higher bar allows for testing 16 combinations.
- The baseline holds the same stocks through the same years.
- Weekly, monthly, Breakout and Breakdown signals are not tested yet, so they stay Unproven.
- Results are overstated by survivorship bias, and the dashboard says so.

## Forecasts and factors

- Papers decide which factors are included. The model learns the weights from past data.
- Published effects are not used as weights. McLean & Pontiff (2016): returns 26% lower out
  of sample and 58% lower after publication. Hou, Xue & Zhang (2020): 65% of 452 anomalies
  fail t = 1.96, and 82% fail 2.78. Harvey, Liu & Zhu (2016): new factors need t above 3.0.
- Effect sizes appear only when read from the paper. Other factors cite the paper only.
- Flat means a next-day move within 0.10%. The 90% range uses the stock's last 250 days.
- Buy or Sell candidate needs the 20-day ranking to pass walk-forward testing after costs.
- Yahoo Finance is excluded: no licensed plan was found, and it is the lowest-ranked source.
- News, options and insider data are in the register but not connected.

## Long-term analysis

- Figures come from SEC company facts and link to their filing. Foreign filers using IFRS
  are not covered, so their figures show Not verified.
- A figure counts from the day after it was filed, and its first-reported version is used.
- DCF: 10 years, growth fading to the terminal rate. Default base growth is the 3-year
  revenue growth, limited to 0 to 15%. Bear and Bull sit 5 points either side. The 9%
  required return and 2.5% terminal growth are assumptions, and users can change them all.
- The insider factor is a simpler measure than Cohen, Malloy & Pomorski: net open-market
  buying, ignoring planned sales. Their published figure does not apply to it directly.

## Decision support

- The pre-trade checklist shows Pass, Caution or Not verified, and is never scored.
- The 15% margin of safety, 10% single-stock limit, 1% trade risk and debt limit are common
  rules of thumb chosen as defaults, not tested results.
- Factor test passes for size, volatility, beta and largest daily gain are distrusted. The
  stock list holds only today's largest companies, which favours past small, wild winners.

## Chart patterns

- Double tops and bottoms, head and shoulders (both ways) and ascending and descending
  triangles are found by fixed rules. A turning point counts only after 5 later candles.
- They are backtested like other signals and feed the model as one factor. Lo, Mamaysky &
  Wang (2000) found some information in such patterns, 1962 to 1996. Flags and cups are not
  built. The rule thresholds are choices, set before testing.

## Known risks

- The 500-symbol limit counts unique symbols per month. Stocks that leave the list also count.
- Tiingo's delisted coverage is partial. TWTR (left the market in 2022) has prices, but
  LEHMQ (2008) has none. The stock list also comes from today's SEC file, so it contains
  no companies that have since failed. Milestone 4 must handle this survivorship bias.
- The SEC ticker file looks ordered by company size, but the SEC does not promise that.
- Daily FRED series (DGS2, DGS10) reject full version history, so only later changes are kept.
- Conflict detection needs a second price source, so it cannot run yet.
- Adjusted prices are not stored. Milestone 3 derives them from dividends and splits.
- Options data for the implied move is undecided. Decide at Milestone 5.
- The build workspace cannot reach Tiingo, SEC or FRED directly. Live checks run on
  GitHub Actions and are read from their logs.
- Render's free dashboard sleeps after 15 minutes idle and takes about a minute to wake.
