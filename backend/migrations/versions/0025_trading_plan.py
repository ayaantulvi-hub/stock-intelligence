"""Records for the trading plan: stop changes, closed trades, and trailing stop tests.

Revision ID: 0025
Revises: 0024
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE stop_changes (
          id serial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          old_stop double precision,
          new_stop double precision,
          changed_at timestamptz NOT NULL DEFAULT now()
        );
        -- The exit price is the latest stored close when the holding was removed, an estimate.
        CREATE TABLE closed_trades (
          id serial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          shares double precision NOT NULL,
          buy_price double precision NOT NULL,
          exit_price double precision,
          exit_market_date date,
          closed_at timestamptz NOT NULL DEFAULT now()
        );
        ALTER TABLE stop_studies ADD COLUMN trails boolean NOT NULL DEFAULT false;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE stop_studies DROP COLUMN trails")
    op.execute("DROP TABLE closed_trades")
    op.execute("DROP TABLE stop_changes")
