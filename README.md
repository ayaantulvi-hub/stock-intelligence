# Stock Intelligence Platform

A web app for verified market data, chart signals, forecasts and long-term cases.
It never places trades and never claims certainty.

**Status: Milestone 3 of 8.** The app collects verified data and shows charts and
rule-based signals. Signals stay Unproven until backtesting exists. No forecasts yet.
See [docs/decisions.md](docs/decisions.md).

## How it runs online

| Part | Where | Notes |
|---|---|---|
| Scheduled data updates | GitHub Actions, `update-data.yml` | Prices after each US close, filings and economic data daily |
| Database | Neon | `DATABASE_URL` |
| Dashboard | Render, `render.yaml` and `Dockerfile` | Sign in with any username and `DASHBOARD_PASSWORD` |

GitHub secrets: `DATABASE_URL`, `TIINGO_API_TOKEN`, `FRED_API_KEY`, `SEC_CONTACT_EMAIL`.

To run an update by hand, open **Actions → Update data → Run workflow**. A failed feed
shows on the dashboard, and the run log ends with a report of what is stored.

## Run it on your own computer (optional)

## What you need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), or your own PostgreSQL 16
- [uv](https://docs.astral.sh/uv/), which installs Python and its packages
- [Node.js](https://nodejs.org/) 22 or later

## Run it

Run the API and the dashboard each in their own terminal. Commands start in the repository root.

1. Set up configuration. Open `.env` and change `change-me` in both places.

   ```
   cp .env.example .env
   ```

2. Start the database.

   ```
   docker compose up -d db
   ```

3. Install the backend and create the tables.

   ```
   cd backend
   uv sync
   uv run alembic upgrade head
   ```

4. Start the API.

   ```
   cd backend
   uv run uvicorn stockintel.main:app --port 8000
   ```

5. Load data. Add your keys to `.env` first.

   ```
   cd backend
   uv run python -m stockintel.ingest universe
   uv run python -m stockintel.ingest prices --limit 45
   uv run python -m stockintel.ingest filings
   uv run python -m stockintel.ingest economic
   ```

6. Start the dashboard, then open http://localhost:5173.

   ```
   cd frontend
   npm install
   npm run dev
   ```

The dashboard should show OK for Database, Database schema and Scheduled updates.

## Run the tests

The backend tests need a real, disposable PostgreSQL database. **They wipe it.** They
refuse to run unless its name contains `test`.

```
docker compose exec db createdb -U stockintel stockintel_test
cd backend
TEST_DATABASE_URL=postgresql+psycopg://stockintel:YOUR_PASSWORD@localhost:5432/stockintel_test uv run pytest
uv run ruff check .
```

On Windows PowerShell, set `$env:TEST_DATABASE_URL = "..."` first, then run `uv run pytest`.

```
cd frontend
npm test
```

## Layout

| Path | Purpose |
|---|---|
| `backend/src/stockintel/` | API, ingestion, validation and database code |
| `backend/src/stockintel/providers/` | Replaceable connectors for each data source |
| `backend/migrations/` | Database schema changes |
| `backend/tests/` | Backend tests. Fixtures stay here, out of production code |
| `frontend/src/` | React dashboard |
| `docs/decisions.md` | Scope, data providers, stack and open questions |

## Rules this project keeps

- Secrets live in `.env`, which git ignores.
- Missing data shows "Not verified". Nothing is guessed or filled in.
- A failure shows as an error, never as a fallback value.
