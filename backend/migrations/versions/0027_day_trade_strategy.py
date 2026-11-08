"""Name the strategy on each day trading test, now that there are two.

Revision ID: 0027
Revises: 0026
"""

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE day_trade_tests ADD COLUMN strategy text NOT NULL DEFAULT 'TJR'")


def downgrade() -> None:
    op.execute("ALTER TABLE day_trade_tests DROP COLUMN strategy")
