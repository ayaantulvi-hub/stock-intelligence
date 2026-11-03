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
