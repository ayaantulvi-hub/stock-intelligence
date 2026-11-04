"""Company events from 8-K filings, and the user's own judgments.

Revision ID: 0013
Revises: 0012
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE filing_events (
          id bigserial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          accession_number text NOT NULL,
          form text NOT NULL,
          filing_date date NOT NULL,
          items text NOT NULL,
          document_url text NOT NULL,
          UNIQUE (security_id, accession_number)
        );
        CREATE INDEX filing_events_latest ON filing_events (security_id, filing_date DESC);
        CREATE TRIGGER filing_events_append_only BEFORE UPDATE OR DELETE ON filing_events
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        CREATE TABLE judgments (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          view text NOT NULL CHECK (view IN ('buy', 'hold', 'sell', 'unsure')),
          reason text NOT NULL,
          changes_mind text NOT NULL,
          price double precision NOT NULL,
          market_date date NOT NULL,
          system_call text NOT NULL
        );
        CREATE TRIGGER judgments_append_only BEFORE UPDATE OR DELETE ON judgments
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE judgments; DROP TABLE filing_events;")
