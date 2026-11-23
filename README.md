# Stock Intelligence Platform

[![Tests](https://github.com/ayaantulvi-hub/stock-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/ayaantulvi-hub/stock-intelligence/actions/workflows/ci.yml)

A private research tool for one individual investor. Every trading day it collects free,
verified data on about 480 large US companies (prices, SEC filings, economic statistics and
news) and gives each stock one call: Buy, Keep, Sell or Leave alone. Its main job is to show
honestly whether a method works before acting on it. Every idea is tested on past data the
model never saw, after trading costs, against a simple baseline, and the result is shown
whether it passed or failed. Most ideas failed, and the app says "No reliable edge" when they
do. It never places trades and is not financial advice.

**See it:** [screenshots and a walkthrough](docs/DEMO.md). They use synthetic data, so no
real prices or holdings are shown.

## Contents

- [Architecture](#architecture)
- [Methods](#methods)
- [Results](#results)
- [Limitations](#limitations)
- [Run it locally](#run-it-locally)
- [Run the tests](#run-the-tests)
- [How it runs online](#how-it-runs-online)
- [Explaining the project](docs/EXPLAIN.md)
- [Data and licensing](#data-and-licensing)

## Architecture

```mermaid
flowchart LR
  subgraph Sources["Free data sources (ranked by trust)"]
    SEC["SEC EDGAR<br/>filings, company facts"]
    FRED["FRED<br/>economic series"]
    FIN["FINRA, House Clerk,<br/>Federal Register"]
    TII["Tiingo<br/>daily prices"]
    ALP["Alpaca<br/>closes, intraday"]
    NEWS["Publisher RSS feeds"]
  end
  subgraph Ingest["Ingestion (providers/)"]
    P["One replaceable provider<br/>per source"]
  end
  subgraph Check["Validation"]
    V["Gaps, outliers, stale data,<br/>source conflicts"]
  end
  subgraph Store["PostgreSQL (Neon)"]
    DB[("Append-only tables<br/>with source, URL and times")]
  end
  subgraph Engines
    C["Charts and signals"]
    F["Factor ranking<br/>and forecasts"]
    L["Long-term cases<br/>and DCF"]
    B["Backtests, model<br/>comparison, stop study"]
    LED["Forecast ledger<br/>(cannot be edited)"]
  end
  SCH["Scheduler: GitHub Actions,<br/>started hourly by cron-job.org"]
  UI["Dashboard (React + FastAPI),<br/>password protected"]
  Sources --> P --> V --> DB
  DB --> C & F & L & B
  F --> LED --> DB
  SCH -. runs .-> P & F & B
  DB --> UI
```

| Layer | Code |
|---|---|
| Providers | [`backend/src/stockintel/providers/`](backend/src/stockintel/providers) |
| Ingestion and validation | [`ingest.py`](backend/src/stockintel/ingest.py), [`validation.py`](backend/src/stockintel/validation.py), [`conflicts.py`](backend/src/stockintel/conflicts.py) |
| Storage | [`backend/migrations/`](backend/migrations/versions). Database triggers reject edits to stored records |
| Engines | [`charts.py`](backend/src/stockintel/charts.py), [`forecast.py`](backend/src/stockintel/forecast.py), [`longterm.py`](backend/src/stockintel/longterm.py), [`backtest.py`](backend/src/stockintel/backtest.py), [`compare.py`](backend/src/stockintel/compare.py) |
| Scheduler | [`.github/workflows/`](.github/workflows) |
| Dashboard | [`frontend/src/`](frontend/src), served by [`main.py`](backend/src/stockintel/main.py) |

## Methods

**Walk-forward testing.** A model is trained only on data from before each test year, then
judged on that year. A gap of 40 days between training and test data stops 20-day outcomes
overlapping. Test years run from 2015.
([`compare.py`](backend/src/stockintel/compare.py), `folds`)

**Hold-out years.** The last two calendar years are never used to choose a model. Several
models compete on the earlier years. The winner is then checked once on the held-back years,
because testing many models makes a lucky winner likely.
([`compare.py`](backend/src/stockintel/compare.py), `HOLDOUT_YEARS = 2`)

**The t ≥ 3 bar.** A result counts only if its t-score is at least 3.0, not the usual 1.96.
- Harvey, Liu & Zhu argue that, given how many factors have been tried, a new one needs a
  t-score above 3.0, and that "most claimed research findings in financial economics are
  likely false" ([NBER w20592](https://www.nber.org/papers/w20592)).
- Hou, Xue & Zhang re-ran 447 published anomalies. 64% were insignificant at the 5% level and
  85% at t = 3 ([NBER w23394](https://www.nber.org/papers/w23394)).
- McLean & Pontiff studied 97 predictors. Returns were 26 percentage points lower out of
  sample and 58 lower after publication
  ([CFA Institute summary](https://rpc.cfainstitute.org/research/cfa-digest/2016/06/does-academic-research-destroy-stock-return-predictability-digest-summary)).
  So published effect sizes are never used as weights. The model learns weights from our own
  data.

One exception: the test of caution rules (`overrides.py`) uses t ≥ 2.

**Costs.** Every simulated trade enters at the next day's open and pays 0.10% round trip
(`COST_BPS = 10` in [`backtest.py`](backend/src/stockintel/backtest.py)). That cost is an
assumption, not a measured figure.

**Baselines.** A signal is compared with holding the same stocks over the same days. A ranking
is compared with the average stock. A forecast is compared with simply predicting the usual
rate.

**Look-ahead protection.**
- A company figure counts from the day after it was filed, and its first-reported version is
  used, not later corrections.
- Economic readings are used only from the day after their date, or later where the
  publisher is slower (the dollar index is lagged 7 days).
- A planted-future-data test proves the check catches leaks
  ([`test_backtest.py`](backend/tests/test_backtest.py),
  `test_planted_look_ahead_is_caught`; also `test_factors_do_not_look_ahead` in
  [`test_forecast.py`](backend/tests/test_forecast.py)).
- Forecasts are only written before the US market opens. A database trigger also rejects
  any forecast created after its target session has closed, and any later edit or deletion
  ([migration 0004](backend/migrations/versions/0004_forecasts.py)).

**Survivorship-bias reconstruction.** Today's stock list holds only companies that survived
and grew, which flatters any backtest. To reduce this, each company's yearly public float
from its SEC filings rebuilds who was large at the time. A stock enters a test only from when
it ranked in about the top 1,000, using figures known by that April
([`ingest.py`](backend/src/stockintel/ingest.py), `eligibility` in
[`backtest.py`](backend/src/stockintel/backtest.py)). It does not bring back companies that
failed or were bought; see [Limitations](#limitations).

## Results

All figures below are summary statistics from the latest stored test run (21 November 2026),
printed by [`results_summary.py`](backend/src/stockintel/results_summary.py), or written in
[`docs/decisions.md`](docs/decisions.md). Each line names the code that produced it.

### 1. No candlestick pattern beat holding the same stocks after costs

- **What was tested:** 32 patterns at 1-day and 5-day horizons: 64 tests and 716,629 signals.
- **Result:** none reached t ≥ 3. The best was t = 1.55, on 52 signals. Only 3 of the 64
  beat the baseline at all.
- **Code:** [`candles.py`](backend/src/stockintel/candles.py), tests in
  [`test_candles.py`](backend/tests/test_candles.py).

### 2. Chart signals: one clear pass

- **What was tested:** 13 signals at several horizons, 28 tests in all: moving-average
  crosses, MACD, RSI, engulfing candles, triangles, double tops and bottoms, and head and
  shoulders.
- **Passes:** two met the edge rule.
  - **RSI recovery, 20 days:** 9,872 cases, win rate 60.9% against a 57.7% baseline, average
    +2.0% against +1.4%.
  - **RSI rollover (bearish), 20 days:** mixed. It fell more often than the baseline (43.0%
    against 41.1% up), but its average move was *less* negative (−1.0% against −1.6%).
- **Code:** [`backtest.py`](backend/src/stockintel/backtest.py),
  [`signals.py`](backend/src/stockintel/signals.py).

### 3. No model passed on the held-back years

Eight models ranked stocks on their chance of beating the average stock over 20 days. Test
years were 2015–2026, with 154 test dates, and 2025–2026 were held back.

| Model | t-score, choice years | Spread, choice years | Spread, held-back years | Passed |
|---|---|---|---|---|
| Random forest (chosen) | 0.56 | +0.46% | +1.94% | No |
| Factor families, boosted | −0.24 | +0.34% | +1.56% | No |
| Gradient boosting | −0.88 | +0.24% | +1.95% | No |
| Factor families, linear | −1.00 | +0.06% | +1.55% | No |
| Average of all models | −1.02 | +0.17% | +1.85% | No |
| Linear model | −1.35 | −0.27% | +1.48% | No |
| Neural network | −1.94 | −0.22% | +0.92% | No |
| Factor families, equal weight | −5.94 | +0.26% | +1.95% | No |

Spread means top-ranked minus bottom-ranked stocks, after costs. No model reached t ≥ 3 on
the choice years, so the app labels its ranking unproven.

Calibration on years the model was not trained on: the top tenth of rankings beat the average
stock 54.2% of the time (4,082 cases), the bottom tenth 47.6% (3,928 cases). It's a gap, but
the test above says it isn't reliable.
([`compare.py`](backend/src/stockintel/compare.py), tests in
[`test_compare.py`](backend/tests/test_compare.py))

### 4. Factor families: no family clearly helped

The model's 35 factors are grouped into 9 families. Leaving each family out in turn changed
results by too little to matter: every |t| was under 1.9, and the verdict was "No clear
effect" for all 9.

Four single factors passed t ≥ 3:

| Factor | t-score |
|---|---|
| Company size | −5.68 |
| Illiquidity | +5.47 |
| Dollar volume | −4.15 |
| Accruals | −3.23 |

The size and liquidity passes are distrusted. A stock list of today's largest companies
favours past small winners, which is exactly what those factors reward.
([`families.py`](backend/src/stockintel/families.py),
[`forecast.py`](backend/src/stockintel/forecast.py); see
[decisions.md](docs/decisions.md#decision-support))

### 5. Whole-market timing failed

A model of whether the average stock rises over the next 20 days, from economy-wide readings
(yield curve, credit spread, VIX and others), scored t = −1.47 over 154 test dates. It did
worse than the base rate on the held-back years. It is shown on the site but changes no call.
([`regime.py`](backend/src/stockintel/regime.py), tests in
[`test_core_logic.py`](backend/tests/test_core_logic.py))

### 6. Stops: wider was better, no stop was best on average

- **What was tested:** 50,557 trades, each held up to 20 days. Stops were set at a multiple
  of the stock's average daily range.

| Stop | Average return | Win rate | Stopped out |
|---|---|---|---|
| None | +1.34% | 57.5% | 0% |
| 4 ranges | +1.15% | 56.1% | 17.5% |
| 3 ranges | +1.05% | 53.5% | 28.1% |
| 2 ranges | +0.85% | 46.4% | 44.8% |
| 1.5 ranges | +0.68% | 39.5% | 55.9% |

- **Trailing stops** did worse at every width.
- **The catch:** stops did limit the worst single trade (−88% with no stop, −44% to −59%
  with one). Survivorship bias also favours holding, because companies that collapsed are
  missing from the test.
- **Code:** [`stops.py`](backend/src/stockintel/stops.py), tests in
  [`test_stops.py`](backend/tests/test_stops.py).

### 7. Two published day-trading methods failed

Both were tested on three years of 5-minute bars, 2023–2026. R is the money
risked on each trade.

| Strategy | Trades | Average result | t-score | Verdict |
|---|---|---|---|---|
| Opening-range breakout | 16,747 | −0.04 R | −4.43 | No reliable edge |
| TJR-style setup | 723 | −0.24 R | −4.77 | No reliable edge |

([`day_trading.py`](backend/src/stockintel/day_trading.py),
[`orb.py`](backend/src/stockintel/orb.py),
[`intraday.py`](backend/src/stockintel/intraday.py))

### 8. A factor added and removed in one day

An inflation-report factor (each stock's past reaction on CPI days, times the latest
surprise) was built, tested and dropped. It scored t = −0.69 over 111 dates. It stays in the
factor list marked "Tested: no reliable edge".
([`forecast.py`](backend/src/stockintel/forecast.py), `cpi_columns` and
`event_sensitivity`, with tests in [`test_forecast.py`](backend/tests/test_forecast.py))

### Forward track record

The live ledger started on 6 November 2026. By 20 November it held 5,225 forecasts over 11
sessions. Of the 4,750 already scored, 88.3% closed inside the stated 90% range. That is too
short to judge anything; see below.

## Limitations

- **Survivorship bias remains.** The public-float rebuild stops today's winners being tested
  before they were large. It cannot add companies that failed, were bought or left the
  market: the free data has no list of them. Every backtest here is therefore flattered, most
  of all those that favour small or falling stocks.
- **Free data only.** Tiingo's free plan allows 50 requests an hour. There are no options
  data, analyst forecasts or a point-in-time list of index members, all of which are paid.
  Intraday data comes from one exchange (IEX).
- **Daily data.** The main model uses end-of-day prices. It can't see moves within a day.
- **The forward track record is under 60 days.** The app's own rule is that a reliability
  grade needs 60 trading days. Until then, the live results are an early sign, not evidence.
- **Costs are assumed.** 0.10% round trip may be low for a small account.
- **Not tested against a market crash** larger than those in 2015–2026.

## Run it locally

You need [Docker](https://www.docker.com/products/docker-desktop/) (or PostgreSQL 16),
[uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 22. Commands start in the
repository root.

```
cp .env.example .env              # then change both "change-me" values and add your free keys
docker compose up -d db
cd backend && uv sync && uv run alembic upgrade head
uv run uvicorn stockintel.main:app --port 8000          # API
uv run python -m stockintel.ingest universe             # load data (needs keys)
uv run python -m stockintel.ingest prices --limit 45
cd ../frontend && npm install && npm run dev             # dashboard on http://localhost:5173
```

## Run the tests

The backend tests need a disposable PostgreSQL database. **They wipe it**, and they refuse to
run unless its name contains `test`.

```
docker compose exec db createdb -U stockintel stockintel_test
cd backend
TEST_DATABASE_URL=postgresql+psycopg://stockintel:YOUR_PASSWORD@localhost:5432/stockintel_test \
  uv run pytest --cov=stockintel
uv run ruff check .
cd ../frontend && npm test
```

GitHub Actions runs all of this on every push ([`ci.yml`](.github/workflows/ci.yml)).

**Latest run, 23 November 2026:**
- Backend: 479 tests pass, plus 1 known failure recorded as expected (a rounding bug in the
  market check's t-score, left unfixed so the decision method doesn't change). Line coverage
  75%.
- Frontend: 46 tests pass. Line coverage about 75%, branch coverage 54%.

## How it runs online

| Part | Where | Cost |
|---|---|---|
| Hourly data updates | GitHub Actions `update-data.yml`, started by cron-job.org | Free: the repository is public, so minutes are unlimited |
| Daily decisions | First update after 10:50 UTC on each US trading day | Free |
| Weekly backtests | `backtest.yml` and `day-trading-test.yml`, Saturdays | Free |
| Database | Neon free plan | Free up to 1 GB storage, 100 compute hours and 5 GB transfer a month |
| Dashboard | Render free web service, password protected | Free; sleeps when idle, so the first load takes about a minute |

Setup steps, privacy rules and a table of failures with their fixes are in
[docs/operations.md](docs/operations.md).

## Data and licensing

- **No market data is stored in this repository.** It contains code only. The figures above
  are summary statistics, not redistributed data.
- **Tiingo's free terms** don't allow redistributing its data, and require crediting Tiingo.
- **Some FRED series are owned by others** (VIX by Cboe; S&P 500, Nasdaq and Dow; Moody's
  spreads) and are used for personal research only. This product uses the FRED® API but is
  not endorsed or certified by the Federal Reserve Bank of St. Louis.
- **News headlines** belong to their publishers. They are read privately and never published.
- **Third-party code** notices are in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- **Design decisions** and the reasons for them are in [docs/decisions.md](docs/decisions.md).
