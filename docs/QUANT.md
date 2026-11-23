# Quant lab

Five classic quantitative ideas, each built from first principles on daily prices for about
480 large US stocks (2010–2026), and tested the same way. Results below are from the stored
run of 23 November 2026, printed by
[`quant/run.py`](../backend/src/stockintel/quant/run.py) and shown on the dashboard's Quant
lab page.

## How every study is judged

- **Engine** ([`engine.py`](../backend/src/stockintel/quant/engine.py)):
  - a position decided at one day's close earns the next day's return;
  - every trade costs 0.10%, and shorts pay a 0.5% yearly borrowing fee (both assumptions);
  - the Sharpe ratio is shown with its standard error ([Lo, 2002](https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html)).
- **Metrics** ([`metrics.py`](../backend/src/stockintel/quant/metrics.py)): match the
  independent `empyrical` library in the tests.
- **Verdict** ([`evaluate.py`](../backend/src/stockintel/quant/evaluate.py)): a t-score of at
  least 3 on the earlier years, with Newey-West standard errors because daily results are not
  independent. The result must also still hold on the last two calendar years, which are held
  back. Parameters are the published or textbook values, fixed before testing.
- **Look-ahead check:** every later return is flipped in sign, and the weights up to that day
  must not change. A planted cheating rule fails this check in the tests.
- **Stocks:** a stock is tradeable only in years it was large by SEC public-float filings, as
  known at the time.

## Results

### 1. Moving-average crossover (50/200 days)

| | Crossover | Hold every tradeable stock |
|---|---|---|
| Sharpe ratio | 0.90 | 1.02 |
| Worst fall | −28.7% | −38.7% |

**No reliable edge.** It earned significantly less than holding everything (t = −3.5) and
also lost on the held-back years. It did cut the worst fall, by about 10 points: the usual
trend-following trade.

### 2. Volatility targeting

Exposure is set monthly from last month's risk, capped at 2×, in returns above the Fed funds
rate ([Moreira & Muir, 2017](https://www.nber.org/papers/w22208)).

| | Variance-managed | Volatility target | Unmanaged |
|---|---|---|---|
| Sharpe ratio | 0.92 | 0.91 | 0.91 |
| Worst fall | −26.9% | −26.5% | −38.8% |
| Alpha t-score | 1.12 | 0.93 | — |

**No reliable edge in return**, as later research predicted
([DeMiguel et al., 2024](https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf)).
It did cut the worst fall by about 12 points.

### 3. Pairs trading (statistical arbitrage)

- **Setup:** pairs are chosen on 12 months and traded for 6, with top 20 pairs per window,
  both stocks in the same industry, entry at 2 standard deviations and exit when the gap
  closes.
- **Fills:** each order waits one day.
- **Returns:** on committed capital.
- **Two ways of choosing pairs:** the distance method
  ([Gatev, Goetzmann & Rouwenhorst, 2006](https://econpapers.repec.org/RePEc:oup:rfinst:v:19:y:2006:i:3:p:797-827))
  and Engle-Granger cointegration.

| Method | Sharpe ratio | Worst fall | t-score |
|---|---|---|---|
| Distance | −0.11 | −22.0% | −0.69 |
| Cointegration | 0.22 | −43.6% | 0.31 |

**No reliable edge with either method.** That fits the published decline: monthly profits fell
from 0.86% (1962–88) to 0.24% (2003–09)
([Do & Faff, 2010](https://ideas.repec.org/a/taf/ufajxx/v66y2010i4p83-95.html)), and costs and
borrowing fees take the rest.

### 4. Monte Carlo Value at Risk

Each day, 10,000 simulated next-day returns are drawn from the past 500 days, giving the 95%
Value at Risk of the all-stocks portfolio. Over 3,686 days:

| Simulation | Breach rate (target 5%) | Breach-rate test (Kupiec) | Bunching test (Christoffersen) | Both together (conditional coverage) | Verdict |
|---|---|---|---|---|---|
| Historical bootstrap | 4.9% | p = 0.86 | p < 0.001 | p < 0.001 | Rejected: breaches bunch together |
| Normal | 4.8% | p = 0.58 | p < 0.001 | p < 0.001 | Rejected: breaches bunch together |
| EWMA normal (RiskMetrics 0.94) | 5.4% | p = 0.24 | p = 0.063 | p = 0.089 | Not rejected |

The "both together" column is Christoffersen's (1998) joint test, added on 23 November 2026 and
reported for reference only: the verdict still uses the two separate tests, as set before the
results were seen. It agrees with them.

This is the clearest finding in the lab. All three models get the *number* of bad days about
right, but the two that weight every past day equally miss *when* they happen: their breaches
arrive in runs, during turbulent spells. The model that weights recent days more passes both
tests, and its breaches are smaller (an extra 0.68% loss on a breach day, against 0.96%). The
bunching test raises false alarms about 6% of the time at this sample size rather than 5%;
the tests check this.

### 5. Market panic detector

The detector tracks, over rolling 63-day windows:
- the average correlation between stocks;
- the top eigenvalue's share;
- the absorption ratio: the share of total variance explained by the top fifth of
  eigenvectors. One fifth is a choice made here.

A warning fires when the absorption ratio's 15-day average rises 1 standard deviation above
its one-year average.

- **It catches crashes as they happen.** The median correlation is 0.29. It peaked at 0.74 on
  16 March 2020, during the COVID crash.
- **Half of the worst 5% of months had a warning beforehand,** against 29% of all days, which
  echoes Kritzman and colleagues' finding
  ([summary](https://www.liverpool.ac.uk/media/livacuk/schoolofmanagement/research/economics/Application,Absorption,Ratio.pdf)).
- **But it fired often, and on average the next month was slightly *better* after a warning**
  (+0.46%, t = 0.69). On the held-back years it was slightly worse (−0.50%).

**No reliable edge as a timing signal.**

## Limitations

- **Survivorship bias:** the stock list is today's companies. Ones that failed or were bought
  are missing, which flatters holding strategies and the pairs tests.
- **Assumed costs:** 0.10% per trade and 0.5% a year to borrow. Real costs vary by stock and
  account.
- **Daily closing prices only:** no intraday entries or exits.
- **Simplified pairs trading:** weights are rebalanced daily instead of holding each leg's
  shares, and one window is traded at a time.
- **One panic signal:** a single set of choices (63 days, top fifth, 1 standard deviation).
  Searching over many settings would only find a lucky one.
- **Data terms:** prices come from Tiingo, whose free terms don't allow redistribution, so
  only summary statistics are published here.
