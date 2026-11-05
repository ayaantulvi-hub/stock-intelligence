"""Daily record of news warnings, so the rule can be tested later.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE news_warnings (
          day date NOT NULL,
          subject text NOT NULL,
          bad integer NOT NULL,
          outlets integer NOT NULL,
          title text NOT NULL,
          url text NOT NULL,
          PRIMARY KEY (day, subject)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE news_warnings")
