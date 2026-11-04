"""Alerts, watchlist, practice trades, journal and Fed meetings.

Revision ID: 0009
Revises: 0008
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE alerts (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          ticker text,
          kind text NOT NULL,
          message text NOT NULL,
          dedupe_key text NOT NULL UNIQUE,
          sent boolean NOT NULL DEFAULT false
        );
        CREATE TABLE watchlist (
          security_id integer PRIMARY KEY REFERENCES securities (id),
          added_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE TABLE practice_trades (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          side text NOT NULL CHECK (side IN ('buy', 'sell')),
          shares double precision NOT NULL CHECK (shares > 0),
          price double precision NOT NULL CHECK (price > 0),
          market_date date NOT NULL,
          reason text NOT NULL
        );
        CREATE TRIGGER practice_trades_append_only BEFORE UPDATE OR DELETE ON practice_trades
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        CREATE TABLE journal_entries (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          decision text NOT NULL CHECK (decision IN ('buy', 'sell', 'hold', 'skip')),
          reason text NOT NULL,
          price double precision NOT NULL,
          market_date date NOT NULL
        );
        CREATE TRIGGER journal_entries_append_only BEFORE UPDATE OR DELETE ON journal_entries
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        CREATE TABLE fed_meetings (
          decision_date date PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id)
        );
        DROP TABLE fomc_dates;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        CREATE TABLE fomc_dates (
          announced date PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id)
        );
        DROP TABLE fed_meetings;
        DROP TABLE journal_entries;
        DROP TABLE practice_trades;
        DROP TABLE watchlist;
        DROP TABLE alerts;
        """
    )
