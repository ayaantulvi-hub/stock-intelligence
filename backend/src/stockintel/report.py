"""Print what is stored, with provenance, so a scheduled run can be checked from its log."""

from sqlalchemy import text

from stockintel import queries
from stockintel.config import get_settings
from stockintel.db import get_engine
from stockintel.status import get_status


def main() -> None:
    engine = get_engine()
    with engine.connect() as conn:
        for table in (
            "securities",
            "fetches",
            "price_bars",
            "filings",
            "economic_observations",
            "company_facts",
            "insider_transactions",
            "validation_issues",
        ):
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            print(f"{table}: {count}")
        size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar()
        print(f"database_mb: {size / 1_000_000:.1f}")
        kinds = conn.execute(
            text("SELECT kind, count(*) FROM validation_issues GROUP BY kind ORDER BY kind")
        ).all()
        print("issues:", {kind: count for kind, count in kinds})
    print(
        "status healthy:", get_status(engine, get_settings().worker_stale_after_seconds)["healthy"]
    )
    for feed in queries.feeds(engine):
        print(
            "feed:",
            feed["feed"],
            feed["source"],
            feed["status"],
            feed["records_added"],
            feed["message"],
        )
    sample = queries.stock(engine, "AAPL")
    if sample and sample["bars"]:
        bar = sample["bars"][0]
        print("AAPL stale:", sample["stale"], "expected:", sample["latest_expected_session"])
        print(
            "AAPL latest:",
            {
                key: str(bar[key])
                for key in (
                    "market_date",
                    "market_timestamp",
                    "source",
                    "source_url",
                    "retrieved_at",
                    "data_status",
                )
            },
        )
    if sample and sample["filings"]:
        filing = sample["filings"][0]
        print(
            "AAPL filing:",
            {
                key: str(filing[key])
                for key in (
                    "form",
                    "filing_date",
                    "document_url",
                    "source",
                    "source_url",
                    "retrieved_at",
                )
            },
        )
    for row in queries.economic(engine):
        print(
            "economic:",
            row["series_id"],
            row["observation_date"],
            row["realtime_start"],
            row["source"],
            row["retrieved_at"],
        )


if __name__ == "__main__":
    main()
