"""Latest prices of funds that track the main US indices.

Revision ID: 0022
Revises: 0021
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE market_quotes (
          id bigserial PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          ticker text NOT NULL,
          quoted_at timestamptz NOT NULL,
          price double precision NOT NULL,
          previous_close double precision NOT NULL,
          UNIQUE (ticker, quoted_at)
        );
        CREATE INDEX market_quotes_latest ON market_quotes (ticker, quoted_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE market_quotes")
