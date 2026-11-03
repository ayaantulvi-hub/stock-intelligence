"""SEC company facts and insider transactions.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE company_facts (
          id bigserial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          tag text NOT NULL,
          unit text NOT NULL,
          period_start date,
          period_end date NOT NULL,
          value double precision NOT NULL,
          accession_number text NOT NULL,
          fiscal_period text,
          form text NOT NULL,
          filed date NOT NULL,
          document_url text NOT NULL,
          UNIQUE NULLS NOT DISTINCT (security_id, tag, period_start, period_end, accession_number)
        );
        CREATE INDEX ix_company_facts_lookup ON company_facts (security_id, tag, period_end);

        CREATE TABLE insider_transactions (
          id bigserial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          accession_number text NOT NULL,
          line integer NOT NULL,
          owner text NOT NULL,
          title text,
          transaction_date date NOT NULL,
          filed date NOT NULL,
          code text NOT NULL,
          shares double precision NOT NULL,
          price double precision,
          planned_sale boolean NOT NULL,
          document_url text NOT NULL,
          UNIQUE (accession_number, line)
        );
        CREATE INDEX ix_insider_security ON insider_transactions (security_id, filed DESC);
        CREATE TABLE insider_documents (
          accession_number text PRIMARY KEY,
          read_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TRIGGER company_facts_append_only BEFORE UPDATE OR DELETE ON company_facts
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        CREATE TRIGGER insider_transactions_append_only
          BEFORE UPDATE OR DELETE ON insider_transactions
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE insider_documents")
    op.execute("DROP TABLE insider_transactions")
    op.execute("DROP TABLE company_facts")
