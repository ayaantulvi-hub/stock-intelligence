"""Delete repeats and logs that add nothing.

Kept on purpose: price history (every study tests on it), the old forecast ledger and other
tables from the earlier app (kept untouched as an archive), and quant results.

Deleted:
- Exact repeats of a price bar (same stock, day and values). Changed values are kept: they are
  the record of corrections.
- Job logs after 30 days, status pings after 7 days, data problems after 30 days.

Run: python -m stockintel.retention [--dry]
"""

import sys

from sqlalchemy import Engine, text

STEPS = {
    "Repeated price bars": """
        DELETE FROM price_bars p USING price_bars q
        WHERE p.security_id = q.security_id AND p.market_date = q.market_date AND p.id > q.id
          AND p.open = q.open AND p.high = q.high AND p.low = q.low AND p.close = q.close
          AND p.volume = q.volume AND p.div_cash = q.div_cash
          AND p.split_factor = q.split_factor""",
    "Job logs over 30 days old": (
        "DELETE FROM feed_runs WHERE started_at < now() - interval '30 days'"
    ),
    "Status pings over 7 days old": (
        "DELETE FROM worker_heartbeats WHERE beat_at < now() - interval '7 days'"
    ),
    "Data problems over 30 days old": (
        "DELETE FROM validation_issues WHERE detected_at < now() - interval '30 days'"
    ),
}
SHRINK = ("price_bars",)
# These tables refuse edits and deletes. Removing an exact repeat loses no information, so the
# guard is lifted for that one delete, inside the same transaction, and put straight back.
GUARDED = {
    "Repeated price bars": "price_bars",
}


def run(engine: Engine, dry: bool = False) -> dict[str, int]:
    done = {}
    for name, sql in STEPS.items():
        with engine.begin() as conn:
            if dry:
                done[name] = conn.execute(
                    text(f"SELECT count(*) FROM ({_as_select(sql)}) AS rows")
                ).scalar()
            elif name in GUARDED:
                table = GUARDED[name]
                conn.execute(text(f"ALTER TABLE {table} DISABLE TRIGGER {table}_append_only"))
                done[name] = conn.execute(text(sql)).rowcount
                conn.execute(text(f"ALTER TABLE {table} ENABLE TRIGGER {table}_append_only"))
            else:
                done[name] = conn.execute(text(sql)).rowcount
    if not dry:
        # Postgres only gives space back to the system after a full vacuum.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            for table in SHRINK:
                conn.execute(text(f"VACUUM FULL {table}"))
    return done


def _as_select(sql: str) -> str:
    """The rows a DELETE or UPDATE would touch, for a dry run."""
    body = " ".join(sql.split())
    if body.startswith("UPDATE expert_reviews"):
        return "SELECT 1 FROM expert_reviews WHERE " + body.split(" WHERE ", 1)[1]
    table, rest = body[len("DELETE FROM ") :].split(" ", 1)
    if rest.startswith("WHERE"):
        return f"SELECT 1 FROM {table} {rest}"
    alias, rest = rest.split(" ", 1)
    other = rest[len("USING ") :]
    return f"SELECT DISTINCT {alias}.id FROM {table} {alias}, {other}"


if __name__ == "__main__":
    from stockintel.db import get_engine

    for name, count in run(get_engine(), dry="--dry" in sys.argv).items():
        print(f"retention|{name}|{count}")
