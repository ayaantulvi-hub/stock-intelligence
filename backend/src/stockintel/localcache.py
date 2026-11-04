"""A local copy of the large append-only tables, so a job downloads only new rows.

The free database allows 5 GB of transfer a month, and the price table alone is over 100 MB.
Rows in these tables are never changed, so anything already copied stays correct.
GitHub Actions keeps the folder between runs. With STOCKINTEL_CACHE unset, every read is full.
"""

import os
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine, text

COLUMNS = {
    "price_bars": """id, security_id, market_date, open, high, low, close, volume, div_cash,
                     split_factor""",
    "company_facts": """id, security_id, tag, unit, period_start, period_end, value,
                        accession_number, fiscal_period, form, filed, document_url""",
    "insider_transactions": """id, security_id, filed, code, shares, price, owner,
                               planned_sale""",
}


def _read(engine: Engine, table: str, after: int) -> pd.DataFrame:
    query = f"SELECT {COLUMNS[table]} FROM {table} WHERE id > :after ORDER BY id"
    with engine.connect() as conn:
        return pd.read_sql(text(query), conn, params={"after": after})


def load(engine: Engine, table: str) -> pd.DataFrame:
    """Every row of an append-only table, oldest first."""
    folder = os.environ.get("STOCKINTEL_CACHE")
    if not folder:
        return _read(engine, table, 0)
    path = Path(folder) / f"{table}.pkl"
    old = pd.read_pickle(path) if path.exists() else None
    last = 0 if old is None or old.empty else int(old["id"].max())
    new = _read(engine, table, last)
    if old is None or old.empty:
        frame = new
    elif new.empty:
        return old
    else:
        frame = pd.concat([old, new], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_pickle(path)
    return frame


def daily_bars(engine: Engine) -> dict[int, pd.DataFrame]:
    """The newest stored version of each day's bar, per security, oldest first."""
    bars = load(engine, "price_bars")
    latest = bars.sort_values("id").drop_duplicates(["security_id", "market_date"], keep="last")
    columns = ["market_date", "open", "high", "low", "close", "volume", "div_cash", "split_factor"]
    return {
        security_id: group[columns].sort_values("market_date").reset_index(drop=True)
        for security_id, group in latest.groupby("security_id")
    }


def facts_by_security(engine: Engine) -> dict[int, pd.DataFrame]:
    facts = load(engine, "company_facts")
    return {
        security_id: group.drop(columns=["id", "security_id"]).reset_index(drop=True)
        for security_id, group in facts.groupby("security_id")
    }
