"""Economic release dates, short interest, Congress trades and override tests.

Revision ID: 0028
Revises: 0027
"""

from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO data_sources (name, trust_rank, base_url) VALUES
          ('FINRA', 1, 'https://api.finra.org'),
          ('House Clerk', 1, 'https://disclosures-clerk.house.gov');
        CREATE TABLE economic_releases (
          name text NOT NULL,
          release_date date NOT NULL,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          PRIMARY KEY (name, release_date)
        );
        CREATE TABLE short_interest (
          security_id integer NOT NULL REFERENCES securities (id),
          settlement_date date NOT NULL,
          short_shares double precision NOT NULL,
          previous_short_shares double precision,
          avg_daily_volume double precision,
          days_to_cover double precision,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          PRIMARY KEY (security_id, settlement_date)
        );
        -- One row per trade line in a House Periodic Transaction Report. Amounts stay ranges.
        CREATE TABLE congress_trades (
          id bigserial PRIMARY KEY,
          doc_id text NOT NULL,
          member text NOT NULL,
          owner text,
          ticker text,
          asset text NOT NULL,
          action text NOT NULL,
          trade_date date,
          filed_date date,
          amount text,
          days_to_file integer,
          url text NOT NULL,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          UNIQUE (doc_id, asset, action, trade_date, amount)
        );
        CREATE TABLE congress_reports (
          doc_id text PRIMARY KEY,
          member text NOT NULL,
          filed_date date,
          read_ok boolean NOT NULL,
          note text
        );
        CREATE TABLE override_tests (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL DEFAULT now(),
          rule text NOT NULL,
          blocked integer NOT NULL,
          blocked_mean double precision,
          others integer NOT NULL,
          others_mean double precision,
          t_stat double precision,
          verdict text NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE override_tests;
        DROP TABLE congress_reports;
        DROP TABLE congress_trades;
        DROP TABLE short_interest;
        DROP TABLE economic_releases;
        DELETE FROM data_sources WHERE name IN ('FINRA', 'House Clerk');
        """
    )
