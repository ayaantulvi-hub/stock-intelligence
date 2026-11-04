"""A planned sell date for each holding.

Revision ID: 0016
Revises: 0015
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE positions ADD COLUMN sell_by date")


def downgrade() -> None:
    op.execute("ALTER TABLE positions DROP COLUMN sell_by")
