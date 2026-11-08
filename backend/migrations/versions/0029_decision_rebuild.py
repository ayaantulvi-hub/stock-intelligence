"""Factor family tests, ranking calibration, the market check, and family scores per forecast.

Revision ID: 0029
Revises: 0028
"""

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE family_tests (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          family text NOT NULL,
          change double precision NOT NULL,
          t_stat double precision NOT NULL,
          verdict text NOT NULL
        );
        CREATE TABLE rank_calibration (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          model text NOT NULL,
          low double precision NOT NULL,
          high double precision NOT NULL,
          rate double precision NOT NULL,
          n integer NOT NULL
        );
        CREATE TABLE market_checks (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          edge boolean NOT NULL,
          t_stat double precision,
          holdout_gain double precision,
          test_dates integer NOT NULL,
          chance double precision,
          state text NOT NULL,
          readings jsonb NOT NULL
        );
        -- New forecasts also carry a plain chance of beating the average stock and the family
        -- scores behind it. Old rows keep these empty: the ledger is never edited.
        ALTER TABLE forecasts ADD COLUMN beat_chance double precision;
        ALTER TABLE forecasts ADD COLUMN families jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE forecasts DROP COLUMN families;
        ALTER TABLE forecasts DROP COLUMN beat_chance;
        DROP TABLE market_checks;
        DROP TABLE rank_calibration;
        DROP TABLE family_tests;
        """
    )
