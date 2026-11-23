"""SYNTHETIC DEMO DATA ONLY. Seeds a local demo database with invented companies and random-walk
prices, so dashboard screenshots show no real market data, headlines or holdings.
Every row is tagged with the source 'SYNTHETIC demo data (not real)'."""

import os

import numpy as np
from sqlalchemy import create_engine, text

from stockintel.market import calendar, session_close

URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://stockintel:change-me@localhost:5432/stockintel_demo"
)
SOURCE = "SYNTHETIC demo data (not real)"
SECTORS = {
    3674: "chips",
    7372: "software",
    2834: "pharma",
    1311: "energy",
    6022: "banks",
    3711: "autos",
}
NAMES = [
    "Alder",
    "Birch",
    "Cedar",
    "Dogwood",
    "Elm",
    "Fir",
    "Ginkgo",
    "Hazel",
    "Juniper",
    "Larch",
    "Maple",
    "Oak",
    "Pine",
    "Rowan",
    "Spruce",
    "Teak",
    "Walnut",
    "Willow",
    "Yew",
    "Aspen",
    "Beech",
    "Cypress",
    "Hemlock",
    "Linden",
    "Magnolia",
    "Poplar",
    "Redwood",
    "Sequoia",
    "Sumac",
    "Tupelo",
    "Acacia",
    "Baobab",
    "Cork",
    "Ebony",
    "Holly",
    "Kauri",
    "Laurel",
    "Mahogany",
    "Olive",
    "Palm",
]


def main() -> None:
    if "demo" not in URL:
        raise SystemExit("Refusing: DATABASE_URL must point at a database named with demo")
    rng = np.random.default_rng(7)
    engine = create_engine(URL)
    days = calendar().sessions_in_range("2012-01-03", "2026-11-20")
    n = len(days)
    market = rng.normal(0.0004, 0.011, n)
    sector_moves = {sic: rng.normal(0, 0.008, n) for sic in SECTORS}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO data_sources (name, trust_rank, base_url) VALUES (:n, 4, "
                "'https://example.invalid/synthetic') ON CONFLICT DO NOTHING"
            ),
            {"n": SOURCE},
        )
        fetch = conn.execute(
            text(
                """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
               SELECT id, 'https://example.invalid/synthetic', now(), 'end_of_day'
               FROM data_sources WHERE name = :n RETURNING id"""
            ),
            {"n": SOURCE},
        ).scalar()
        for i, base in enumerate(NAMES):
            sic = list(SECTORS)[i % len(SECTORS)]
            ticker = f"DM{base[:2].upper()}{i % 10}"
            cik = 900000 + i
            sid = conn.execute(
                text(
                    """INSERT INTO securities (ticker, cik, name, exchange, universe_rank, sic)
                   VALUES (:t, :c, :n, 'DEMO', :r, :s) RETURNING id"""
                ),
                {"t": ticker, "c": cik, "n": f"{base} Synthetic Co (demo)", "r": i + 1, "s": sic},
            ).scalar()
            beta = rng.uniform(0.6, 1.5)
            drift = rng.normal(0.0002, 0.0002)
            vol = rng.uniform(0.008, 0.02)
            r = drift + beta * market + sector_moves[sic] + rng.normal(0, vol, n)
            close = 50 * rng.uniform(0.5, 3) * np.exp(np.cumsum(r))
            open_ = close * np.exp(rng.normal(0, 0.004, n))
            high = np.maximum(open_, close) * np.exp(np.abs(rng.normal(0, 0.006, n)))
            low = np.minimum(open_, close) * np.exp(-np.abs(rng.normal(0, 0.006, n)))
            volume = rng.lognormal(14, 0.4, n)
            rows = [
                {
                    "s": sid,
                    "f": fetch,
                    "d": d.date(),
                    "ts": session_close(d.date()),
                    "o": float(o),
                    "h": float(h),
                    "l": float(lo),
                    "c": float(c),
                    "v": float(v),
                }
                for d, o, h, lo, c, v in zip(days, open_, high, low, close, volume)
            ]
            conn.execute(
                text(
                    """INSERT INTO price_bars (security_id, fetch_id, market_date, market_timestamp,
                     open, high, low, close, volume, div_cash, split_factor)
                   VALUES (:s, :f, :d, :ts, :o, :h, :l, :c, :v, 0, 1)"""
                ),
                rows,
            )
            for year in range(2009, 2027):
                conn.execute(
                    text(
                        """INSERT INTO historic_float (year, cik, public_float, size_rank, fetch_id)
                       VALUES (:y, :c, :p, :r, :f)"""
                    ),
                    {"y": year, "c": cik, "p": 1e10 / (i + 1), "r": i + 1, "f": fetch},
                )
    print("seeded", len(NAMES), "synthetic companies over", n, "sessions")


if __name__ == "__main__":
    main()
