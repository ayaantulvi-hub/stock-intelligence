"""Results of testing stop distances.

Revision ID: 0010
Revises: 0009
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE stop_studies (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          stop_multiple double precision,
          trades integer NOT NULL,
          avg_return double precision NOT NULL,
          win_rate double precision NOT NULL,
          worst_return double precision NOT NULL,
          stopped_share double precision NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE stop_studies")
