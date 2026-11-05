"""The Keep or Sell now answer for each holding, kept per day to spot changes.

Revision ID: 0018
Revises: 0017
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE holding_calls (
          ticker text NOT NULL,
          day date NOT NULL,
          call text NOT NULL,
          reason text NOT NULL,
          PRIMARY KEY (ticker, day)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE holding_calls")
