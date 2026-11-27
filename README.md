# Quant Lab

[![Tests](https://github.com/ayaantulvi-hub/stock-intelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/ayaantulvi-hub/stock-intelligence/actions/workflows/ci.yml)

Classic quantitative-finance ideas, built from first principles in Python and tested the way
a sceptical reviewer would: on daily prices for 480 large US companies (2010–2026), and on the
whole US market's daily returns since 1926. On a hand-written backtest engine, the lab runs:

- volatility targeting (four published versions) and a 100-year test of it;
- pairs trading (statistical arbitrage), momentum and low-volatility stocks;
- trend following;
- Monte Carlo Value at Risk (five models, including GARCH and filtered historical simulation);
- factor momentum across 11 investing styles, US and developed markets;
- mean reversion (Bollinger bands) and breakout (Donchian channels, the Turtle rules);
- a market panic detector built from eigenvalues of the correlation matrix.

**What held up** (2 of 23 tests, against a bar set before testing):

- **Factor momentum** (Ehsani & Linnainmaa, 2022), on 11 factors from 1927: t = 4.15 after
  costs, positive on the held-back years. Over the paper's own period (from 1964) the Sharpe
  ratio is 0.77 (t = 5.04), and it stayed positive after the paper's data ended in 2015.
- **EWMA Value at Risk:** the right number of bad days, and no clustering.
- **Near miss:** volatility targeting on 100 years of data reached an alpha t-score of 2.55,
  short of 3.

Every idea faces the same test:
- it is judged on data it was not designed on;
- trading costs are paid;
- it must beat a simple benchmark by a t-score of at least 3;
- it must still work on two held-back years.

Most published ideas fail that bar, and this project reports the failures as well as the
passes. Data collection runs on its own every hour, and the studies rerun every week. It is
a learning and research project, not financial advice, and it places no trades.

- **Results and methods:** [docs/QUANT.md](docs/QUANT.md)
- **Two findings written up as research notes:** [docs/RESEARCH.md](docs/RESEARCH.md)
- **Screenshots and a walkthrough** (synthetic data): [docs/DEMO.md](docs/DEMO.md)
- **Interview questions about the project:** [docs/EXPLAIN.md](docs/EXPLAIN.md)

## Architecture

```mermaid
flowchart LR
  subgraph Sources["Free data sources"]
    SEC["SEC EDGAR<br/>stock list, company sizes"]
    TII["Tiingo<br/>daily prices"]
    ALP["Alpaca<br/>latest closes"]
    FRED["FRED<br/>Fed funds rate"]
    KF["French Data Library<br/>US market since 1926"]
  end
  P["Providers<br/>(one per source)"]
  V["Validation<br/>gaps, outliers, stale data"]
  DB[("PostgreSQL<br/>append-only, with source<br/>and time on every row")]
  subgraph Lab["Quant lab"]
    E["Backtest engine<br/>and metrics"]
    S["Studies: trend, volatility,<br/>pairs, VaR, panic"]
    J["One verdict rule"]
  end
  SCH["Scheduler: GitHub Actions,<br/>hourly data and weekly studies"]
  UI["Dashboard (React + FastAPI),<br/>password protected"]
  Sources --> P --> V --> DB --> E --> S --> J --> DB
  SCH -. runs .-> P & S
  DB --> UI
```

| Layer | Code |
|---|---|
| Providers | [`providers/`](backend/src/stockintel/providers) |
| Collection and validation | [`ingest.py`](backend/src/stockintel/ingest.py), [`validation.py`](backend/src/stockintel/validation.py) |
| Point-in-time stock lists, price adjustment | [`prices.py`](backend/src/stockintel/prices.py), [`quant/data.py`](backend/src/stockintel/quant/data.py) |
| Engine, metrics, verdict | [`engine.py`](backend/src/stockintel/quant/engine.py), [`metrics.py`](backend/src/stockintel/quant/metrics.py), [`evaluate.py`](backend/src/stockintel/quant/evaluate.py) |
| Studies | [`studies.py`](backend/src/stockintel/quant/studies.py), [`vol.py`](backend/src/stockintel/quant/vol.py), [`pairs.py`](backend/src/stockintel/quant/pairs.py), [`var.py`](backend/src/stockintel/quant/var.py), [`panic.py`](backend/src/stockintel/quant/panic.py) |
| Storage | [`backend/migrations/`](backend/migrations/versions). Triggers reject edits to stored rows |
| Scheduler | [`.github/workflows/`](.github/workflows) |
| Dashboard | [`frontend/src/`](frontend/src), served by [`main.py`](backend/src/stockintel/main.py) |

## Methods

- **No look-ahead.**
  - A position decided at one day's close earns the next day's return.
  - Each study's rules are checked by flipping the sign of every later return: weights up to
    that day must not change, and a planted cheating rule fails the check in the tests.
  - Company sizes count only from the April after the year they describe.
- **Costs.** 0.10% on every trade and 0.5% a year to borrow shares for shorting. Both are
  assumptions, not measured figures.
- **The t ≥ 3 bar.** Harvey, Liu & Zhu argue that, after so many ideas have been tried, a
  new one needs a t-score above 3 ([NBER w20592](https://www.nber.org/papers/w20592)).
  t-scores use Newey-West standard errors, because one day's result is not independent of
  the next.
- **Hold-out years.** The last two calendar years are reported separately and must also be
  positive. Parameters are the published or textbook values, fixed before testing, so
  nothing is tuned on the results.
- **Survivorship.** A stock is tradeable only in years when SEC public-float filings show it
  was large at the time.
- **Metrics.** Hand-written, and checked in the tests against the independent `empyrical`
  library. The Sharpe ratio is shown with its standard error
  ([Lo, 2002](https://ideas.repec.org/a/taf/ufajxx/v58y2002i4p36-52.html)).

## Results

From the stored run of 27 November 2026, with details and sources in
[docs/QUANT.md](docs/QUANT.md):

| Study | Verdict | In one line |
|---|---|---|
| Trend following (50/200-day) | No reliable edge | Lower Sharpe than holding everything (0.90 vs 1.02), but a smaller worst fall |
| Volatility targeting, monthly (two versions) | No reliable edge | Same Sharpe (about 0.91), worst fall cut from −38.8% to about −27% |
| Volatility targeting, conditional | No reliable edge | Slightly worse than holding over 2015–2026 |
| Volatility targeting, daily EWMA | No reliable edge | Best version: worst fall −21.8% against −38.8%, but alpha t only 1.12 |
| Volatility targeting, 100 years (four versions) | No reliable edge | Alpha t 1.53 to 2.55, short of 3; held-back years negative for three of four |
| Trend following, 100 years | No reliable edge | Higher Sharpe (0.49 vs 0.45) and worst fall −64% vs −85%, but less return |
| Momentum (months t-12 to t-2) | No reliable edge | Sharpe −0.05 after costs |
| Low volatility (calmest 10%) | No reliable edge | Sharpe 0.67 vs 0.93, alpha t −0.19 |
| **Factor momentum, 11 factors** | **Edge** | **t = 4.15 from 1927; Sharpe 0.77 and t = 5.04 from 1964** |
| Mean reversion (Bollinger 20, 2 sd) | No reliable edge | Sharpe −0.19 after costs, worst fall −56% |
| Breakout (Donchian 55/20) | No reliable edge | Sharpe 0.79 vs 1.06 for holding everything |
| Breakout, 100 years | No reliable edge | Sharpe 0.61 vs 0.45 and worst fall −29% vs −85%, but less return |
| Pairs trading, distance | No reliable edge | Sharpe −0.11 after costs |
| Pairs trading, cointegration | No reliable edge | Sharpe 0.22 ± 0.25, and a −43.6% fall |
| Value at Risk, historical | Rejected | Right number of breaches, but they bunch together |
| Value at Risk, normal | Rejected | Same problem |
| Value at Risk, EWMA | **Not rejected** | Passes both the breach-rate and bunching tests |
| Value at Risk, filtered historical | Rejected | Halves back-to-back breaches, but narrowly fails the bunching test |
| Value at Risk, GJR-GARCH-t | Rejected | Best timing, but too many breaches (6.5%) |
| Panic detector | No reliable edge | Spots crashes as they happen, but doesn't predict the next month |

## Limitations

- **Survivorship bias remains.** The stock list is today's companies. Ones that failed or
  were bought are missing, which flatters every result, especially holding strategies and
  pairs trading.
- **Free data only.** Tiingo's free plan allows 50 requests an hour. There is no options
  data and no list of delisted stocks.
- **Daily closing prices only.** No intraday entries or exits.
- **Assumed costs.** Real costs vary by stock and broker.
- **Fixed settings.** Each study uses one set of settings. Searching over many would only
  find a lucky one.

## Run it locally

You need [Docker](https://www.docker.com/products/docker-desktop/) (or PostgreSQL 16),
[uv](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org/) 22.

```
cp .env.example .env              # then change both "change-me" values and add your free keys
docker compose up -d db
cd backend && uv sync && uv run alembic upgrade head
uv run python -m stockintel.ingest universe             # stock list (SEC)
uv run python -m stockintel.ingest history              # past company sizes (SEC)
uv run python -m stockintel.ingest prices --limit 45    # repeat hourly until all are loaded
uv run python -m stockintel.ingest economic             # Fed funds rate (FRED)
uv run python -m stockintel.quant.run                   # run every study and store results
uv run uvicorn stockintel.main:app --port 8000          # API
cd ../frontend && npm install && npm run dev             # dashboard on http://localhost:5173
```

No keys? [demo/](demo) builds a labelled synthetic database, so the whole pipeline and the
dashboard run with no real data.

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

GitHub Actions runs all of this on every push ([`ci.yml`](.github/workflows/ci.yml)), and
prints coverage.

## How it runs online

| Part | Where | Cost |
|---|---|---|
| Hourly data | GitHub Actions `update-data.yml`, started by cron-job.org | Free: public repository |
| Weekly studies | `backtest.yml`, Saturdays | Free |
| Database | Neon free plan | Free up to 1 GB, 100 compute hours and 5 GB transfer a month |
| Dashboard | Render free web service, password protected | Free; sleeps when idle |

Setup, privacy rules and recovery steps are in [docs/operations.md](docs/operations.md).

## Data and licensing

- **No market data is stored in this repository.** It contains code only, and the figures
  above are summary statistics.
- **Tiingo:** its free terms don't allow redistributing its data, and require crediting
  Tiingo. So the dashboard, which charts derived series, stays private.
- **FRED:** this product uses the FRED® API but is not endorsed or certified by the Federal
  Reserve Bank of St. Louis.
- **History:** the project began as a stock-decision app. Its record of design decisions,
  including why it became the Quant Lab, is in [docs/decisions.md](docs/decisions.md).
