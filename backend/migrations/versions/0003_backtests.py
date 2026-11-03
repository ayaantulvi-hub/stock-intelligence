"""Backtest runs and results.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE backtest_runs (
          id serial PRIMARY KEY,
          finished_at timestamptz NOT NULL DEFAULT now(),
          stocks integer NOT NULL,
          first_date date NOT NULL,
          last_date date NOT NULL,
          cost_bps double precision NOT NULL,
          note text NOT NULL
        );
        CREATE TABLE backtest_results (
          id serial PRIMARY KEY,
          run_id integer NOT NULL REFERENCES backtest_runs (id),
          signal text NOT NULL,
          direction text NOT NULL,
          horizon integer NOT NULL,
          sample_size integer NOT NULL,
          win_rate double precision,
          baseline_win_rate double precision,
          avg_return double precision,
          baseline_avg_return double precision,
          oos_sample_size integer NOT NULL,
          oos_win_rate double precision,
          oos_baseline_win_rate double precision,
          oos_avg_return double precision,
          oos_baseline_avg_return double precision,
          edge boolean NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE backtest_results")
    op.execute("DROP TABLE backtest_runs")
