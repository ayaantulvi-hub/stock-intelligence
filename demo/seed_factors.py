"""SYNTHETIC DEMO DATA ONLY: invented daily returns for the ten extra factors used by factor
momentum, so the study and its screen run locally. Pure noise with no persistence built in, so
factor momentum should find no edge here."""

import os

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo"
)
SOURCE = "SYNTHETIC demo data (not real)"
SERIES = {
    "us_smb": "1963-07-01", "us_hml": "1963-07-01", "us_rmw": "1963-07-01", "us_cma": "1963-07-01",
    "us_lt_rev": "1931-01-02", "devx_mkt_rf": "1990-07-02", "devx_smb": "1990-07-02",
    "devx_hml": "1990-07-02", "devx_rmw": "1990-07-02", "devx_cma": "1990-07-02",
}


def main() -> None:
    if "demo" not in URL:
        raise SystemExit("Refusing: DATABASE_URL must point at a database named with demo")
    rng = np.random.default_rng(1964)
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
        rows = []
        for name, start in SERIES.items():
            days = pd.bdate_range(start, "2026-09-30")
            values = rng.normal(0.0001, 0.005, len(days))
            rows += [{"f": fetch, "s": name, "d": d.date(), "v": float(v)} for d, v in zip(days, values, strict=True)]
        conn.execute(
            text("INSERT INTO factor_returns (fetch_id, series, market_date, value) VALUES (:f, :s, :d, :v)"),
            rows,
        )
    print(f"SYNTHETIC: {len(rows)} invented factor returns written to the demo database")


if __name__ == "__main__":
    main()
