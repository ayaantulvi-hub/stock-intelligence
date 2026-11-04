"""Candlestick tests, stored short-term views and reasons for wrong forecasts.

Revision ID: 0015
Revises: 0014
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE candle_tests (
          id bigserial PRIMARY KEY,
          run_at timestamptz NOT NULL,
          pattern text NOT NULL,
          horizon integer NOT NULL,
          signals integer NOT NULL,
          win_rate double precision NOT NULL,
          avg_return double precision NOT NULL,
          extra_return double precision NOT NULL,
          t_stat double precision NOT NULL
        );
        CREATE INDEX candle_tests_latest ON candle_tests (run_at DESC);
        CREATE TABLE forecast_misses (
          forecast_id bigint PRIMARY KEY REFERENCES forecasts (id),
          created_at timestamptz NOT NULL DEFAULT now(),
          reason text,
          change_percent double precision
        );
        CREATE TRIGGER forecast_misses_append_only BEFORE UPDATE OR DELETE ON forecast_misses
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        ALTER TABLE expert_reviews ADD COLUMN short_term jsonb;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE expert_reviews DROP COLUMN short_term;
        DROP TABLE forecast_misses;
        DROP TABLE candle_tests;
        """
    )
