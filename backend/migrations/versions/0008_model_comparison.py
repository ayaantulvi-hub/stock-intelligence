"""Results of testing different model types against each other.

Revision ID: 0008
Revises: 0007
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_comparisons (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          model text NOT NULL,
          test_days integer NOT NULL,
          loss double precision NOT NULL,
          baseline_loss double precision NOT NULL,
          t_stat double precision NOT NULL,
          spread double precision NOT NULL,
          holdout_t_stat double precision,
          holdout_spread double precision,
          worst_year integer,
          worst_year_spread double precision,
          calm_spread double precision,
          stressed_spread double precision,
          selected boolean NOT NULL,
          edge boolean NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE model_comparisons")
