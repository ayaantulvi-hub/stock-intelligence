"""News now comes from publishers' own RSS feeds.

Revision ID: 0020
Revises: 0019
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE data_sources SET name = 'Publisher news feeds', base_url = 'https://www.bbc.co.uk'
        WHERE name = 'GDELT';
        ALTER TABLE news_tone ALTER COLUMN fetch_id DROP NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE news_tone ALTER COLUMN fetch_id SET NOT NULL;
        UPDATE data_sources SET name = 'GDELT', base_url = 'https://www.gdeltproject.org'
        WHERE name = 'Publisher news feeds';
        """
    )
