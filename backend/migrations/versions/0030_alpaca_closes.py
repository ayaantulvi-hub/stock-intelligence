"""Alpaca's consolidated (SIP) daily bars, to fill the latest close for every stock at once.

Revision ID: 0030
Revises: 0029
"""

from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """INSERT INTO data_sources (name, trust_rank, base_url)
           VALUES ('Alpaca (SIP)', 2, 'https://data.alpaca.markets')"""
    )


def downgrade() -> None:
    op.execute("DELETE FROM data_sources WHERE name = 'Alpaca (SIP)'")
