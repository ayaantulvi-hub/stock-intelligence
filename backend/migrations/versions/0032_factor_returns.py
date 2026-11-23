"""Daily US market and risk-free returns from the Kenneth R. French Data Library.

Append-only: a value is stored again only when the library changes it, so revisions keep the
old value. Each row links to its fetch, which records the source URL and retrieval time.

Revision ID: 0032
Revises: 0031
"""

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO data_sources (name, trust_rank, base_url)
        VALUES ('Kenneth R. French Data Library', 2,
                'https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html');
        CREATE TABLE factor_returns (
          id serial PRIMARY KEY,
          fetch_id integer NOT NULL REFERENCES fetches (id),
          series text NOT NULL,
          market_date date NOT NULL,
          value double precision NOT NULL
        );
        CREATE INDEX factor_returns_series_date ON factor_returns (series, market_date, id);
        CREATE TRIGGER factor_returns_append_only BEFORE UPDATE OR DELETE ON factor_returns
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE factor_returns")
    op.execute("DELETE FROM data_sources WHERE name = 'Kenneth R. French Data Library'")
