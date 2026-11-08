"""Clean-up of data that no longer feeds decisions. Every row here is a TEST FIXTURE."""

from sqlalchemy import text

from stockintel import retention


def setup_rows(conn):
    sid = conn.execute(
        text(
            """INSERT INTO securities (ticker, cik, name, exchange, universe_rank)
           VALUES ('AAA', '1', 'AAA', 'NYSE', 1) RETURNING id"""
        )
    ).scalar()
    fetch = conn.execute(
        text(
            """INSERT INTO fetches (source_id, source_url, retrieved_at, data_status)
           SELECT id, 'https://fixture.test', now(), 'end_of_day' FROM data_sources
           LIMIT 1 RETURNING id"""
        )
    ).scalar()
    bar = """INSERT INTO price_bars (fetch_id, security_id, market_date, market_timestamp, open,
               high, low, close, volume, div_cash, split_factor)
             VALUES (:f, :s, '2026-11-06', '2026-11-06', 1, 1, 1, :c, 1, 0, 1)"""
    for close in (10.0, 10.0, 10.5):  # A repeat, then a correction.
        conn.execute(text(bar), {"f": fetch, "s": sid, "c": close})
    fact = """INSERT INTO company_facts (security_id, fetch_id, tag, unit, period_start,
                period_end, value, accession_number, fiscal_period, form, filed, document_url)
              VALUES (:s, :f, 'Revenues', 'USD', '2024-01-01', '2024-12-31', :v, :a, 'FY',
                '10-K', :filed, 'https://fixture.test')"""
    conn.execute(text(fact), {"s": sid, "f": fetch, "v": 100, "a": "a1", "filed": "2025-02-01"})
    conn.execute(text(fact), {"s": sid, "f": fetch, "v": 100, "a": "a2", "filed": "2026-02-01"})
    conn.execute(text(fact), {"s": sid, "f": fetch, "v": 95, "a": "a3", "filed": "2026-02-01"})


def count(engine, sql):
    with engine.connect() as conn:
        return conn.execute(text(sql)).scalar()


def test_repeats_go_and_corrections_stay(engine):
    with engine.begin() as conn:
        setup_rows(conn)
    dry = retention.run(engine, dry=True)
    assert dry["Repeated price bars"] == 1
    assert dry["Company figures repeated in later reports"] == 1
    assert count(engine, "SELECT count(*) FROM price_bars") == 3  # A dry run changes nothing.
    retention.run(engine)
    assert count(engine, "SELECT count(*) FROM price_bars") == 2
    assert count(engine, "SELECT array_agg(close ORDER BY id)::text FROM price_bars") == "{10,10.5}"
    # The first report and the restatement stay; the identical repeat goes.
    assert (
        count(engine, "SELECT array_agg(accession_number ORDER BY id)::text FROM company_facts")
        == "{a1,a3}"
    )


def test_the_guard_is_back_after_cleaning(engine):
    import pytest
    from sqlalchemy.exc import DBAPIError

    with engine.begin() as conn:
        setup_rows(conn)
    retention.run(engine)
    with pytest.raises(DBAPIError, match="append-only"), engine.begin() as conn:
        conn.execute(text("DELETE FROM price_bars"))
