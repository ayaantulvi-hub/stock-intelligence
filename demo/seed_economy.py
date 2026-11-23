"""SYNTHETIC DEMO DATA ONLY: invented economic series so the forecast pipeline can run locally."""

import os

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

from stockintel.ingest import ECONOMIC_SERIES

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo"
)
SOURCE = "SYNTHETIC demo data (not real)"
LEVELS = {
    "DGS2": 3.0,
    "DGS10": 3.5,
    "T10Y3M": 0.8,
    "DFF": 2.5,
    "FEDFUNDS": 2.5,
    "VIXCLS": 18,
    "BAA10Y": 2.0,
    "DCOILWTICO": 70,
    "T10YIE": 2.2,
    "DTWEXBGS": 115,
    "USEPUINDXD": 120,
    "UNRATE": 4.5,
    "CPIAUCSL": 250,
    "GDPC1": 20000,
    "ICSA": 230000,
    "SP500": 3000,
    "NASDAQCOM": 9000,
    "DJIA": 25000,
}


def main() -> None:
    if "demo" not in URL:
        raise SystemExit("Refusing: DATABASE_URL must point at a database named with demo")
    rng = np.random.default_rng(11)
    engine = create_engine(URL)
    days = pd.bdate_range("2005-01-03", "2026-11-20")
    with engine.begin() as conn:
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
               SELECT id, 'https://example.invalid/synthetic', now(), 'end_of_day'
               FROM data_sources WHERE name = :n RETURNING id"""
            ),
            {"n": SOURCE},
        ).scalar()
        for series in ECONOMIC_SERIES:
            level = LEVELS.get(series, 100.0)
            walk = level * np.exp(np.cumsum(rng.normal(0, 0.004, len(days))))
            rows = [
                {"s": series, "f": fetch, "d": d.date(), "v": float(v)} for d, v in zip(days, walk)
            ]
            conn.execute(
                text(
                    """INSERT INTO economic_observations (series_id, fetch_id, observation_date,
                     realtime_start, value) VALUES (:s, :f, :d, :d, :v)"""
                ),
                rows,
            )
    print("seeded", len(ECONOMIC_SERIES), "synthetic series")


if __name__ == "__main__":
    main()
