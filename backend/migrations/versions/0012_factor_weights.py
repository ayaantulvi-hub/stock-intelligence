"""How much each factor counted in the model.

Revision ID: 0012
Revises: 0011
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE factor_weights (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          factor text NOT NULL,
          weight double precision NOT NULL
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE factor_weights")
