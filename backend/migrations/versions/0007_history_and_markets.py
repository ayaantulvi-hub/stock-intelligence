"""Past company sizes, sectors and Fed announcement dates.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE securities ADD COLUMN sic integer;
        CREATE TABLE historic_float (
          year integer NOT NULL,
          cik integer NOT NULL,
          public_float double precision NOT NULL,
          size_rank integer NOT NULL,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          PRIMARY KEY (year, cik)
        );
        CREATE TABLE fomc_dates (
          announced date PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id)
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE fomc_dates")
    op.execute("DROP TABLE historic_float")
    op.execute("ALTER TABLE securities DROP COLUMN sic")
