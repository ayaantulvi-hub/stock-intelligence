# Demo data (synthetic, not real)

Everything here is a **test fixture**, kept out of the app's code paths. It builds a local
database of 40 invented companies with random-walk prices and an invented Fed funds rate, so
the whole pipeline and the dashboard can be shown without real market data. Every row is
stored under the source "SYNTHETIC demo data (not real)", and every screenshot carries a red
banner saying so. The seed scripts refuse to run unless the database name contains "demo".

It is also a null test. On random prices there is nothing to find, so every trading study
should report "No reliable edge", and they do.

```
createdb stockintel_demo                                # as a PostgreSQL user that owns it
cd backend
export DATABASE_URL=postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo
uv run alembic upgrade head
uv run python ../demo/seed_prices.py && uv run python ../demo/seed_economy.py
uv run python -m stockintel.quant.run                   # every study, stored
uv run uvicorn stockintel.main:app --port 8000          # then, in frontend/: npx vite
node ../demo/screenshots.js                             # writes docs/screenshots/
```
