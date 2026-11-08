"""Print the biggest tables, to see where database space goes."""

from sqlalchemy import text

from stockintel.db import get_engine

QUERY = """SELECT relname, pg_total_relation_size(relid) / 1048576.0 AS mb, n_live_tup
           FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 25"""

if __name__ == "__main__":
    with get_engine().connect() as conn:
        for row in conn.execute(text(QUERY)):
            print(f"size|{row.relname}|{row.mb:.1f}|{row.n_live_tup}")
        facts = conn.execute(
            text(
                """SELECT tag, count(*) FROM company_facts GROUP BY tag
               ORDER BY count(*) DESC LIMIT 15"""
            )
        ).all()
        for concept, count in facts:
            print(f"concept|{concept}|{count}")
        print(
            "concepts|",
            conn.execute(text("SELECT count(DISTINCT tag) FROM company_facts")).scalar(),
        )
