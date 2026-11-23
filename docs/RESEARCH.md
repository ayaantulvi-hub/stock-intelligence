# Research notes

Two findings from the quant lab, written as short research notes. All figures come from the
stored run of 23 November 2026. It was produced by
[`quant/run.py`](../backend/src/stockintel/quant/run.py) in
[backtest run 45194837368](https://github.com/ayaantulvi-hub/stock-intelligence/actions/runs/45194837368)
and printed by [`results_summary.py`](../backend/src/stockintel/results_summary.py) in
[run 45195232855](https://github.com/ayaantulvi-hub/stock-intelligence/actions/runs/45195232855).
Prices are from Tiingo, whose terms don't allow redistribution, so only summary statistics
appear here.

---

## Note 1. Getting the number of bad days right is not enough: testing Value at Risk

### Question

A 95% Value at Risk (VaR) says: "on 95% of days, the loss will be smaller than this". Banks
and funds use it to set limits. A model can be wrong in two separate ways. It can be breached
too often, or its breaches can arrive in runs, so that it fails exactly when risk is rising.
Which of three common ways of simulating VaR passes both checks for a portfolio of US stocks?

### Data

- **Portfolio:** daily returns of an equal-weight portfolio of every stock that was large at
  the time, using SEC public-float filings to decide which were large.
- **Prices:** adjusted for splits and dividends, after 0.10% trading costs.
- **Test period:** 3,686 trading days, 27 March 2012 to 20 November 2026.

### Method

Each day, 10,000 possible next-day returns are simulated using only the previous 500 days
([`var.py`](../backend/src/stockintel/quant/var.py)). There are three ways of simulating:

- **Historical bootstrap:** draw past days at random.
- **Normal:** draw from a normal curve with the window's mean and standard deviation.
- **EWMA normal:** a normal curve whose volatility weights recent days more, with decay 0.94
  as in J.P. Morgan's RiskMetrics (1996)
  ([formula](https://metricgate.com/docs/ewma-volatility-riskmetrics/)).

The VaR is the 5th percentile of the simulated returns. A breach is a day whose real return
was worse. Two standard tests, with formulas as documented by
[MathWorks](https://it.mathworks.com/help/risk/overview-of-var-backtesting.html):

- **Kupiec (1995), breach rate:** is the share of breach days believably 5%?
- **Christoffersen (1998), independence:** is a breach more (or less) likely the day after a
  breach? This test is two-sided.

A model is rejected if either p-value is below 0.05. The tests check:
- both formulas against the likelihood written out by hand;
- that a correct model passes on simulated data;
- that waves of volatility break the plain normal model;
- that the forecast for any day is unchanged when later data is altered.

### Result

| | Historical | Normal | EWMA normal |
|---|---|---|---|
| Breaches (of 3,686 days) | 182 | 177 | 200 |
| Breach rate (target 5%) | 4.94% | 4.80% | 5.43% |
| Kupiec p-value | 0.86 | 0.58 | 0.24 |
| Breach rate on the day after a breach | 16.6% | 17.0% | 8.5% |
| Back-to-back breaches | 30 | 30 | 17 |
| Christoffersen p-value | < 0.001 | < 0.001 | 0.063 |
| Average extra loss beyond VaR on a breach day | 0.96% | 0.97% | 0.68% |
| Verdict | Rejected: bunching | Rejected: bunching | Not rejected |

All three models get the overall breach rate right. Judged on the count alone, all three
would pass. But for the two models that treat the last 500 days equally, a breach was more
than three times as likely the day after a breach as on an average day (about 17% against
5%). Their breaches cluster by year:

- **Historical model, breach rate by year:**
  - 12.7% in 2018 and 9.5% in 2020;
  - 0.4% in 2017 and 1.2% in 2023.
- **EWMA model:** between 3.6% and 7.1% in every year.

In plain terms, a model built on a long, equally weighted window is too cautious in calm
years and too relaxed when markets turn. The EWMA model reacts within days, passes both
tests, and loses less beyond its estimate when it is breached.

### Limitations

- **One portfolio, one confidence level, one window length.** Results could differ for a
  single stock, at 99%, or with a different window.
- **Small-sample error in the independence test.** It relies on a chi-square approximation.
  On simulated independent breaches it raised false alarms 8.5% of the time at 1,000 days
  and about 6% at 4,000, against a nominal 5%. With p < 0.001 for the two rejected models,
  this doesn't change the conclusion. The EWMA model's p-value of 0.063 is close to the line.
- **Survivorship bias.** The stock list leaves out companies that later failed. Their crashes
  would add extreme days and probably more breaches for every model.
- **The decay value is not tested.** The EWMA's 0.94 was taken from RiskMetrics, not tuned
  here. No alternative values were tried, so the result isn't the best of many.

---

## Note 2. Does pairs trading still work after costs? Distance against cointegration

### Question

Pairs trading buys the cheaper of two stocks that usually move together and sells the
dearer, betting the gap closes. Gatev, Goetzmann & Rouwenhorst
([2006](https://econpapers.repec.org/RePEc:oup:rfinst:v:19:y:2006:i:3:p:797-827)) reported
annualised excess returns of up to 11% on 1962–2002 data. Do & Faff
([2010](https://ideas.repec.org/a/taf/ufajxx/v66y2010i4p83-95.html)) found monthly profits for
the top 20 pairs falling from 0.86% (1962–88) to 0.24% (2003–09). Does either the original
method or the more statistical cointegration method make money on large US stocks from 2011
to 2026, after realistic costs?

### Data

- **Stocks:** daily adjusted prices for stocks that were large at the time.
- **Pairing rule:** only stocks in the same industry (first two digits of the SEC industry
  code) are paired.
- **Windows:** 32 trading windows of six months, from 31 March 2011 to 20 November 2026
  (3,935 trading days).

### Method

The code is [`pairs.py`](../backend/src/stockintel/quant/pairs.py). Both methods use the same
windows:
- form pairs on 12 months, then trade the top 20 for the next 6;
- open a position at a 2-standard-deviation gap and close it when the gap closes;
- close anything still open on the last day;
- wait one day before each order fills, as in the original paper;
- measure returns on committed capital (all 20 pairs, traded or not).

The two methods:
- **Distance:** pairs with the smallest squared difference between their price paths, each
  path rescaled to start at 1.
- **Cointegration:** pairs whose log-price spread passes an Engle-Granger test at 5%, ranked
  by p-value. The hedge ratio comes from a regression, and trades follow the spread's z-score.

Costs and judging:
- **Costs:** 0.10% per trade and 0.5% a year to borrow the shorted stock. Both are
  assumptions.
- **Pass mark:** the mean daily return must have a Newey-West t-score of at least 3 on
  2011–2024, and stay positive on 2025–26, which was held back.
- **Tests check:**
  - a planted cointegrated pair is found with the right hedge ratio;
  - pairs never cross industries;
  - the opening and closing rules work;
  - no rule uses future prices.

### Result

| | Distance | Cointegration |
|---|---|---|
| Trades | 722 | 951 |
| Share of chosen pairs that traded | 87% | 97% |
| Average days held | 53 | 53 |
| Average return before costs, a year | 0.6% | 3.9% |
| Average cost and borrowing drag, a year | 1.1% | 1.5% |
| Compound return after costs, a year | −0.5% | 1.8% |
| Sharpe ratio (± standard error) | −0.11 (± 0.25) | 0.22 (± 0.25) |
| Worst fall | −22.0% | −43.6% |
| t-score, 2011–2024 | −0.69 | 0.31 |
| Correlation with the stock market | 0.10 | 0.02 |
| Verdict | No reliable edge | No reliable edge |

The first two rows are simple averages. The compound figure is lower than their difference
(for cointegration 1.8%, against 3.9% − 1.5% = 2.4%), because ups and downs reduce compound
growth.

The original distance method barely makes money even before costs (0.6% a year), and costs
turn it negative. Cointegration does better before costs (3.9%), but its Sharpe ratio of
0.22 is within one standard error of zero. It also suffered a 43.6% fall, a large loss for a
strategy meant to be market-neutral. It was indeed almost uncorrelated with the market
(0.02), so it isn't a disguised bet on stocks rising.

There is one result to treat with care. Cointegration's results by period:

| Period | Sharpe ratio |
|---|---|
| 2011–15 | −0.82 |
| 2016–20 | 0.01 |
| 2021–26 | 0.93 |
| Held-back 2025–26 | 1.39 (13.5% a year, t = 2.10) |

It is tempting to say it "works now". But the method was required to pass on the earlier
years first, and it didn't. A t-score of 2.10 over under two years is short of the 3.0 bar.
Picking the best-looking recent stretch after seeing the results is exactly the error that
Harvey, Liu & Zhu ([NBER w20592](https://www.nber.org/papers/w20592)) warn about. The fair
conclusion is that recent results are better and should be watched as new data arrives, not
that the strategy works.

### Limitations

- **Survivorship bias matters most here.** Pairs where one company later collapsed (often
  the losing side of a pair trade) are missing, so real results would likely be worse.
- **Costs are assumed, and simplifications were made.** The trade cost and borrowing fee are
  estimates. Weights are rebalanced daily rather than holding each leg's shares, and only one
  trading window runs at a time.
- **Industry is a rough proxy.** Two digits of the SEC industry code is a coarse grouping.
  Finer groups could produce better pairs, but trying many would raise the risk of a lucky
  result.
- **Daily closing prices only.** Real fills would differ, especially on the day a gap opens.
