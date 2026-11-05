"""News headlines and tone, stored as links only.

Revision ID: 0019
Revises: 0018
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO data_sources (name, trust_rank, base_url)
        VALUES ('GDELT', 3, 'https://www.gdeltproject.org');
        CREATE TABLE news_articles (
          id bigserial PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          subject text NOT NULL,
          url text NOT NULL,
          title text NOT NULL,
          domain text NOT NULL,
          seen_at timestamptz NOT NULL,
          UNIQUE (subject, url)
        );
        CREATE INDEX news_articles_latest ON news_articles (subject, seen_at DESC);
        CREATE TABLE news_tone (
          subject text NOT NULL,
          day date NOT NULL,
          tone double precision NOT NULL,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          PRIMARY KEY (subject, day)
        );
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE news_tone;
        DROP TABLE news_articles;
        DELETE FROM data_sources WHERE name = 'GDELT';
        """
    )
