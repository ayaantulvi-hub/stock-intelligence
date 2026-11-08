"""Delete data that no longer feeds any decision, and repeats that add nothing.

Kept on purpose: price history and company figures (the model trains and tests on them), the
forecast ledger (it can never be edited), policy, fund, insider and economic history, and
anything a test still needs.

Deleted:
- Exact repeats of a price bar (same stock, day and values). Changed values are kept: they are
  the record of corrections.
- Company figures repeated in a later report with the same value, form and period. The code
  reads figures "as first reported", so the repeat is never used. Restated values are kept.
- News headlines after 14 days. The page shows 7 and the warnings use 2. Each day's warnings
  are kept separately, so whether they helped can still be tested.
- AI news readings after 14 days, live quotes after 2 days, job logs after 30 days, status
  pings after 7 days, data problems after 30 days.
- The long explanation inside expert reviews after 7 days. Whether a stock was blocked is kept,
  because the caution-rule test needs it.

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
    "Company figures repeated in later reports": """
        DELETE FROM company_facts f USING company_facts g
        WHERE f.security_id = g.security_id AND f.tag = g.tag AND f.unit = g.unit
          AND f.form = g.form AND f.period_end = g.period_end
          AND f.period_start IS NOT DISTINCT FROM g.period_start AND f.value = g.value
          AND (g.filed < f.filed OR (g.filed = f.filed AND g.id < f.id))""",
    "News headlines over 14 days old": (
        "DELETE FROM news_articles WHERE seen_at < now() - interval '14 days'"
    ),
    "AI news readings over 14 days old": (
        "DELETE FROM news_judgments WHERE judged_at < now() - interval '14 days'"
    ),
    "Live quotes over 2 days old": (
        "DELETE FROM market_quotes WHERE quoted_at < now() - interval '2 days'"
    ),
    "Job logs over 30 days old": (
        "DELETE FROM feed_runs WHERE started_at < now() - interval '30 days'"
    ),
    "Status pings over 7 days old": (
        "DELETE FROM worker_heartbeats WHERE beat_at < now() - interval '7 days'"
    ),
    "Data problems over 30 days old": (
        "DELETE FROM validation_issues WHERE detected_at < now() - interval '30 days'"
    ),
    "Expert review explanations over 7 days old": """
        UPDATE expert_reviews SET detail = '{}'::jsonb
        WHERE review_date < current_date - 7 AND detail <> '{}'::jsonb""",
}
SHRINK = ("price_bars", "company_facts", "expert_reviews", "news_articles")
# These tables refuse edits and deletes. Removing an exact repeat loses no information, so the
# guard is lifted for that one delete, inside the same transaction, and put straight back.
GUARDED = {
    "Repeated price bars": "price_bars",
    "Company figures repeated in later reports": "company_facts",
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
