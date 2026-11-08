"""Results of testing the day trading rules. Only summaries are kept, not minute bars.

Revision ID: 0026
Revises: 0025
"""

from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE day_trade_tests (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL DEFAULT now(),
          source text NOT NULL,
          source_url text NOT NULL,
          data_from date NOT NULL,
          data_to date NOT NULL,
          trades integer NOT NULL,
          mean_r double precision,
          win_rate double precision,
          t_stat double precision,
          baseline_mean_r double precision,
          verdict text NOT NULL,
          detail jsonb NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE day_trade_tests")
