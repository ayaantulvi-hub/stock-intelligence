"""The local copy must match the database and fetch only new rows."""

import pandas as pd
from sqlalchemy import text

from stockintel import localcache


def test_first_read_fills_the_copy_and_later_reads_ask_only_for_new_rows(
    engine, tmp_path, monkeypatch
):
    monkeypatch.setenv("STOCKINTEL_CACHE", str(tmp_path))
    with engine.begin() as conn:
        conn.execute(
            text(
                """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
                   VALUES ('ZZTEST', 999999, 'Fixture', 'Nasdaq', 9999)"""
            )
        )
    localcache.load(engine, "price_bars")
    seen = []
    real = localcache._read
    monkeypatch.setattr(
        localcache, "_read", lambda e, t, after: seen.append(after) or real(e, t, after)
    )
    first = localcache.load(engine, "price_bars")
    last = 0 if first.empty else int(first["id"].max())
    localcache.load(engine, "price_bars")
    assert seen == [last, last]


def test_a_copy_from_another_database_is_thrown_away(engine, tmp_path, monkeypatch):
    monkeypatch.setenv("STOCKINTEL_CACHE", str(tmp_path))
    pd.DataFrame({"id": [10**12]}).to_pickle(tmp_path / "price_bars.pkl")
    assert localcache.load(engine, "price_bars")["id"].max() != 10**12
