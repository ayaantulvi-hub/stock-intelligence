"""SYNTHETIC DEMO DATA ONLY: an invented century of daily market returns, so the 100-year
study and its dashboard screen run locally. Volatility comes in calm and stormy spells, but
there is no built-in reward for timing them, so no strategy should find a real edge here."""

import os

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo"
)
SOURCE = "SYNTHETIC demo data (not real)"


def main() -> None:
    if "demo" not in URL:
        raise SystemExit("Refusing: DATABASE_URL must point at a database named with demo")
    rng = np.random.default_rng(1926)
    days = pd.bdate_range("1926-07-01", "2026-09-30")
    variance, vols = 1e-4, np.empty(len(days))
    shocks = rng.standard_normal(len(days))
    for i in range(len(days)):  # GARCH-like waves of volatility, invented parameters.
        variance = 2e-6 + 0.08 * (vols[i - 1] * shocks[i - 1]) ** 2 + 0.9 * variance if i else variance
        vols[i] = np.sqrt(variance)
    market = 0.0003 + vols * shocks
    engine = create_engine(URL)
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
                   SELECT id, 'https://example.invalid/synthetic', now(), 'end_of_day'
                   FROM data_sources WHERE name = :n RETURNING id"""
            ),
            {"n": SOURCE},
        ).scalar_one()
        conn.execute(
            text(
                """INSERT INTO factor_returns (fetch_id, series, market_date, value)
                   VALUES (:f, :s, :d, :v)"""
            ),
            [
                {"f": fetch, "s": series, "d": day.date(), "v": float(value)}
                for day, m in zip(days, market, strict=True)
                for series, value in (("mkt_rf", m), ("rf", 0.0001))
            ],
        )
    print(f"SYNTHETIC: {len(days)} invented days of market returns written to the demo database")


if __name__ == "__main__":
    main()
