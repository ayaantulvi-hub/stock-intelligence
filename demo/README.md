# Demo data (synthetic, not real)

Everything here is a **test fixture**, kept out of the app's code paths. It builds a local
database of 40 invented companies with random-walk prices and invented economic series, so the
dashboard can be shown without real market data, headlines or anyone's holdings. Every row is
stored under the source "SYNTHETIC demo data (not real)", and every screenshot carries a red
banner saying so.

It also works as a null test: on random data with no signal, the real pipelines find no edge.
Every model fails its test, and the rankings beat the average stock about 50% of the time.

```
createdb stockintel_demo                                # as a PostgreSQL user that owns it
cd backend
export DATABASE_URL=postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo
uv run alembic upgrade head
uv run python ../demo/seed_prices.py && uv run python ../demo/seed_economy.py
for m in backtest "forecast evaluate" compare regime stops candles "forecast daily"; do
  uv run python -m stockintel.$m; done
uv run uvicorn stockintel.main:app --port 8000          # then, in frontend/: npx vite
node ../demo/screenshots.js                             # writes docs/screenshots/
```
