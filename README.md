# Stock Intelligence Platform

A web app for verified market data, chart signals, forecasts and long-term cases.
It never places trades and never claims certainty.

**Status: Milestone 1 of 8.** The app starts and reports its own health. No market
data, signals or forecasts exist yet. See [docs/decisions.md](docs/decisions.md).

## What you need

- [Docker Desktop](https://www.docker.com/products/docker-desktop/), or your own PostgreSQL 16
- [uv](https://docs.astral.sh/uv/), which installs Python and its packages
- [Node.js](https://nodejs.org/) 22 or later

## Run it

Run each of the last three steps in its own terminal. Commands start in the repository root.

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

5. Start the worker.

   ```
   cd backend
   uv run python -m stockintel.worker
   ```

6. Start the dashboard, then open http://localhost:5173.

   ```
   cd frontend
   npm install
   npm run dev
   ```

The dashboard should show OK for Database, Database schema and Worker.
If you stop the worker, it shows Stale after three minutes.

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
| `backend/src/stockintel/` | API, worker, configuration and database code |
| `backend/migrations/` | Database schema changes |
| `backend/tests/` | Backend tests. Fixtures stay here, out of production code |
| `frontend/src/` | React dashboard |
| `docs/decisions.md` | Scope, data providers, stack and open questions |

## Rules this project keeps

- Secrets live in `.env`, which git ignores.
- Missing data shows "Not verified". Nothing is guessed or filled in.
- A failure shows as an error, never as a fallback value.
