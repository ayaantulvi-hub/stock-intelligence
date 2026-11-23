"""Results of the quant lab studies. Append-only: a new run adds rows, old ones stay.

Revision ID: 0031
Revises: 0030
"""

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE quant_results (
          id serial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          study text NOT NULL,
          variant text NOT NULL,
          period text NOT NULL,
          metrics jsonb NOT NULL,
          verdict text NOT NULL,
          settings jsonb NOT NULL
        );
        CREATE INDEX quant_results_study ON quant_results (study, run_at);
        CREATE TRIGGER quant_results_append_only BEFORE UPDATE OR DELETE ON quant_results
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE quant_results")
