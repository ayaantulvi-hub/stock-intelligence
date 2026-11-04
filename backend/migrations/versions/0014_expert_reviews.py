"""Daily expert reviews. The user-entered judgment table was never used, so it goes.

Revision ID: 0014
Revises: 0013
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DROP TABLE judgments;
        CREATE TABLE expert_reviews (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          review_date date NOT NULL,
          agree integer NOT NULL,
          against integer NOT NULL,
          blocked text,
          detail jsonb NOT NULL
        );
        CREATE INDEX expert_reviews_latest ON expert_reviews (security_id, id DESC);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE expert_reviews;
        CREATE TABLE judgments (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          view text NOT NULL,
          reason text NOT NULL,
          changes_mind text NOT NULL,
          price double precision NOT NULL,
          market_date date NOT NULL,
          system_call text NOT NULL
        );
        """
    )
