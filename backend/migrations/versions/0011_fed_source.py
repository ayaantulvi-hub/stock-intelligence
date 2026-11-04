"""Register the Federal Reserve as a data source.

Revision ID: 0011
Revises: 0010
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """INSERT INTO data_sources (name, trust_rank, base_url)
           VALUES ('Federal Reserve', 1, 'https://www.federalreserve.gov')"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM data_sources WHERE name = 'Federal Reserve'")
