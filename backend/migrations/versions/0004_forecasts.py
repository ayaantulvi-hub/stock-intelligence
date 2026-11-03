"""Model evaluations, the forecast ledger and its scores.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE model_evaluations (
          id serial PRIMARY KEY,
          model text NOT NULL,
          finished_at timestamptz NOT NULL DEFAULT now(),
          stocks integer NOT NULL,
          test_days integer NOT NULL,
          first_test date NOT NULL,
          last_test date NOT NULL,
          model_loss double precision NOT NULL,
          baseline_loss double precision NOT NULL,
          t_stat double precision NOT NULL,
          top_minus_bottom double precision,
          edge boolean NOT NULL
        );

        -- The ledger. Rows can be added before the outcome is known and never changed.
        CREATE TABLE forecasts (
          id bigserial PRIMARY KEY,
          created_at timestamptz NOT NULL DEFAULT now(),
          security_id integer NOT NULL REFERENCES securities (id),
          as_of_session date NOT NULL,
          target_session date NOT NULL,
          target_close timestamptz NOT NULL,
          last_close double precision NOT NULL,
          p_up double precision NOT NULL,
          p_flat double precision NOT NULL,
          p_down double precision NOT NULL,
          range_low double precision NOT NULL,
          range_high double precision NOT NULL,
          rank_20d double precision,
          next_day_edge boolean NOT NULL,
          rank_edge boolean NOT NULL,
          confidence text NOT NULL,
          drivers jsonb NOT NULL,
          UNIQUE (security_id, target_session)
        );
        CREATE INDEX ix_forecasts_target ON forecasts (target_session DESC);

        CREATE TABLE forecast_scores (
          forecast_id bigint PRIMARY KEY REFERENCES forecasts (id),
          scored_at timestamptz NOT NULL DEFAULT now(),
          actual_close double precision NOT NULL,
          outcome text NOT NULL CHECK (outcome IN ('up', 'flat', 'down')),
          brier double precision NOT NULL,
          baseline_brier double precision NOT NULL,
          in_range boolean NOT NULL
        );

        CREATE FUNCTION forecast_before_outcome() RETURNS trigger AS $$
        BEGIN
          IF NEW.created_at >= NEW.target_close THEN
            RAISE EXCEPTION 'forecast must be written before its outcome is known';
          END IF;
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER forecasts_before_outcome BEFORE INSERT ON forecasts
          FOR EACH ROW EXECUTE FUNCTION forecast_before_outcome();
        CREATE TRIGGER forecasts_append_only BEFORE UPDATE OR DELETE ON forecasts
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        CREATE TRIGGER forecast_scores_append_only BEFORE UPDATE OR DELETE ON forecast_scores
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE forecast_scores")
    op.execute("DROP TABLE forecasts")
    op.execute("DROP FUNCTION forecast_before_outcome")
    op.execute("DROP TABLE model_evaluations")
