"""An AI reading of each headline, kept with the model that wrote it.

Revision ID: 0024
Revises: 0023
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE news_judgments (
          url text PRIMARY KEY,
          title text NOT NULL,
          domain text NOT NULL,
          seen_at timestamptz NOT NULL,
          judged_at timestamptz NOT NULL DEFAULT now(),
          model text NOT NULL,
          scope text NOT NULL CHECK (scope IN ('market', 'industry', 'company', 'none')),
          industries text[] NOT NULL DEFAULT '{}',
          tickers text[] NOT NULL DEFAULT '{}',
          effect text NOT NULL CHECK (effect IN ('negative', 'positive', 'mixed', 'none')),
          size text NOT NULL CHECK (size IN ('big', 'medium', 'small')),
          why text NOT NULL
        );
        CREATE INDEX news_judgments_latest ON news_judgments (seen_at DESC);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE news_judgments")
