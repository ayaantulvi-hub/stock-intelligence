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

## Reducing survivorship bias

- SEC yearly public float figures rebuild who was large at the time. A stock enters tests
  only from when it ranked in about the top 1,000, using figures known by that April.
- This stops today's winners being tested from before they became large. It does not add
  companies that failed or were bought: their tickers are not in the SEC list, and Tiingo's
  free plan has room for about 20 more symbols a month. Tiingo Power at $30 a month, even
  for one month, would allow loading them if tickers can be found.
- The float data is noisy, as some filers misreport it.
- VIX and the Moody's spread are copyrighted on FRED, so they are for personal use only.

## Model comparison and self-correction

- Linear, random forest, gradient boosting, neural network and an average of all four are
  tested weekly on the same dates, each trained only on earlier data.
- The winner is chosen on earlier years. The last two calendar years are kept out of the
  choice and used as a final check, because testing many models makes luck likely.
- An edge needs a test score of 3.0, a positive spread after costs, and a positive final check.
- General chat AI is not tested: it already knows past outcomes, so a test would be cheating.

## Fed dates

- FRED release 101 returned nearly every day, so it does not identify meetings. Dates now
  come from the Federal Reserve's own calendar pages.

## Tools

- Alerts cover held and watched stocks, and are sent as GitHub issues.
- Practice trades fill at the latest close from a $10,000 pretend balance.
- A reliability grade needs 60 trading days. Overconfidence correction starts at that point.
- Next earnings is an estimate: 91 days after the last quarterly or yearly report.

## Scheduling

- GitHub skipped most scheduled runs, so hourly price runs are started by cron-job.org through
  the GitHub API. It needs a fine-grained token limited to Actions on this repository.
- A second cron-job.org job runs filings, company data and forecasts at 14:50 Dubai time, Tuesday to Saturday.

## Stops

- Suggested stop: just under support if that is 1 to 3 daily ranges away, otherwise 3 average
  daily ranges below the price. Suggested target: twice the risk. These are rules, not
  predictions. Stop distances are tested weekly across all stocks, not per stock.

## Stop test, 4 November 2026

- 27,264 trades on 245 stocks, held up to 60 days. No stop averaged +4.7%, 4 ranges +3.5%,
  3 ranges +3.1%, 2 ranges +2.3%, 1.5 ranges +1.8%. Survivorship bias favours holding, as
  companies that collapsed are missing.
- The no-stop worst trade of -136% is impossible, so some adjusted prices are wrong. Check
  large dividends and spin-offs in the adjustment before relying on worst-case figures.

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

## Company events, judgment and foreign filers

- A payout and a split can share a day (Motorola 2011, Hilton 2017, T-Mobile 2013). The
  payout is in post-split dollars, so adjustment divides the previous close by the split
  factor. Before this fix the factor went negative and created a -136% trade in the stop study.
- Moderna's +177% on 2026-08-19 looked like a bad bar, but outside reports confirm it.
- Banks have no revenue line. Revenue is net interest plus noninterest income. Foreign banks
  report gross income under the gross profit label, so that is used and no gross margin shows.
- Some Canadian filers put yearly accounts on a 6-K, so full-year figures on a 6-K count.
- 20-F filers often trade through receipts, and the receipt ratio is not in the SEC figures.
  Market value, yields, value per share and share-based factors stay Not verified for them.
- SEC 8-K item numbers are stored from the submissions feed. Item 2.02 gives true past
  results days, and the next date is still an estimate because no free official source
  publishes upcoming dates.
- Human judgement is simulated as an expert review: published methods run as written rules
  on stored figures. Altman's danger zone, a Piotroski score of 2 or less, or a serious 8-K
  in 90 days overrides a buy to Hold off. That override is a safety rule, not a tested edge.
  The Piotroski score is also a model factor. The app can't contain every book or video.
- Several insiders buying together is a tested factor. It affects ranking only if it earns
  weight in the weekly model test.

## Staying inside free limits

- Neon's free plan allows 100 compute hours and 5 GB of transfer a month per project. Repeated
  full reads of about 1.1 million price rows suspended the database on 2026-11-04.
- Jobs now keep a copy of the append-only tables in the GitHub Actions cache and fetch only
  rows newer than the copy (localcache.py). The website reads one stock at a time.
- Paid plans are ruled out by the user. The tool must stay free.

## Trading and investing answers

- Each stock gets a short-term trade answer (1 to 5 days, from candlestick patterns) and a
  long-term answer (months to years, from company checks). Daily candles can't time moves
  within a day, so this isn't true day trading.
- Tiingo's free limit of 50 requests an hour rules out intraday data for all stocks.
- Candle patterns are tested weekly against all stocks over the same days, after costs. A
  pattern with a worse result gives no trade.
- Each wrong forecast gets the likeliest reason from stored records, or says no cause is stored.
- The stock page shows what to enter in an order, using TradingView's field names.

## Real-world context

- Added 10-year minus 3-month yields, the Fed funds rate and the Economic Policy Uncertainty
  index from FRED, plus presidential actions from the Federal Register (official, no key).
- Election windows and midterm years come from the date set by law, so nothing leaks from the
  future. Who won an election isn't used, because few elections are in the price history.
- Stock-level rate and policy sensitivity are measured over the past year, up to the day before.
- All of these go through the same weekly tests. A reading earns weight only if it helps.
- A topic label on a presidential action is a keyword match, for display and counting only.

## What changed

- The home page compares the two latest forecast days and expert reviews, and each holding's
  stored Keep or Sell now answer. Stocks held or watched come first and raise an alert.
- A stock with no earlier result isn't reported as a change.
- The first full tests on 480 stocks found no candlestick pattern that beat all stocks after
  costs, so most patterns give no trade.

## News

- GDELT was tried first, but it refused GitHub's shared addresses with its rate limit.
- News now comes from publishers' public RSS feeds, read hourly: BBC, CNBC, MarketWatch, New York
  Times, The Guardian and Financial Times. Only headlines and links are stored, for one
  person's private reading. A feed that fails is reported and the others continue.
- Headlines are matched to all 480 companies by name and to world topics by keyword.
- Mood is a rough count of positive and negative words, not a reading of meaning. It isn't in
  the model. There's no long history to test, so it's stored until it can be tested.
