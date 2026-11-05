"""Quarterly holdings of well-known funds, from SEC Form 13F.

Revision ID: 0023
Revises: 0022
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE fund_filings (
          accession_number text PRIMARY KEY,
          fund_cik integer NOT NULL,
          fund_name text NOT NULL,
          period date NOT NULL,
          filed date NOT NULL
        );
        CREATE TABLE fund_holdings (
          id bigserial PRIMARY KEY,
          accession_number text NOT NULL REFERENCES fund_filings (accession_number),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          security_id integer NOT NULL REFERENCES securities (id),
          fund_cik integer NOT NULL,
          period date NOT NULL,
          filed date NOT NULL,
          shares double precision NOT NULL,
          document_url text NOT NULL,
          UNIQUE (accession_number, security_id)
        );
        CREATE INDEX fund_holdings_security ON fund_holdings (security_id, period DESC);
        CREATE TRIGGER fund_holdings_append_only BEFORE UPDATE OR DELETE ON fund_holdings
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE fund_holdings; DROP TABLE fund_filings;")
