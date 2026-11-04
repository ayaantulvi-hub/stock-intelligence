"""Factor tests and the owner's positions.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE factor_tests (
          id serial PRIMARY KEY,
          tested_at timestamptz NOT NULL DEFAULT now(),
          factor text NOT NULL,
          spread double precision NOT NULL,
          t_stat double precision NOT NULL,
          dates integer NOT NULL
        );
        CREATE TABLE positions (
          security_id integer PRIMARY KEY REFERENCES securities (id),
          shares double precision NOT NULL CHECK (shares > 0),
          buy_price double precision NOT NULL CHECK (buy_price > 0),
          target_price double precision CHECK (target_price > 0),
          stop_price double precision CHECK (stop_price > 0),
          updated_at timestamptz NOT NULL DEFAULT now()
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE positions")
    op.execute("DROP TABLE factor_tests")
