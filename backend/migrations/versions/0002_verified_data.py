"""Verified data: securities, fetch records, prices, filings and economic data.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

APPEND_ONLY = ("fetches", "price_bars", "filings", "economic_observations")


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO data_sources (name, trust_rank, base_url) VALUES
          ('SEC EDGAR', 1, 'https://www.sec.gov'),
          ('FRED', 1, 'https://fred.stlouisfed.org'),
          ('Tiingo', 2, 'https://www.tiingo.com');

        CREATE TABLE securities (
          id serial PRIMARY KEY,
          ticker text NOT NULL UNIQUE,
          cik integer NOT NULL,
          name text NOT NULL,
          exchange text NOT NULL,
          universe_rank integer NOT NULL,
          last_price_fetch_at timestamptz,
          last_filing_fetch_at timestamptz,
          added_at timestamptz NOT NULL DEFAULT now()
        );

        CREATE TABLE feed_runs (
          id serial PRIMARY KEY,
          feed text NOT NULL,
          started_at timestamptz NOT NULL DEFAULT now(),
          finished_at timestamptz,
          status text NOT NULL DEFAULT 'running'
            CHECK (status IN ('running', 'ok', 'partial', 'error')),
          items_attempted integer NOT NULL DEFAULT 0,
          items_ok integer NOT NULL DEFAULT 0,
          records_added integer NOT NULL DEFAULT 0,
          message text
        );
        CREATE INDEX ix_feed_runs_feed_started ON feed_runs (feed, started_at DESC);

        -- One row per successful request. Every stored data point points to its
        -- fetch, which holds the source, source URL and retrieval time.
        CREATE TABLE fetches (
          id bigserial PRIMARY KEY,
          source_id integer NOT NULL REFERENCES data_sources (id),
          source_url text NOT NULL,
          retrieved_at timestamptz NOT NULL,
          data_status text NOT NULL CHECK (data_status IN ('end_of_day', 'delayed', 'live'))
        );

        -- Raw traded values only. Adjusted prices are derived later from div_cash and
        -- split_factor, so a new dividend does not rewrite every past row.
        CREATE TABLE price_bars (
          id bigserial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          market_date date NOT NULL,
          market_timestamp timestamptz NOT NULL,
          open double precision NOT NULL,
          high double precision NOT NULL,
          low double precision NOT NULL,
          close double precision NOT NULL,
          volume double precision NOT NULL,
          div_cash double precision NOT NULL,
          split_factor double precision NOT NULL
        );
        CREATE INDEX ix_price_bars_latest ON price_bars (security_id, market_date DESC, id DESC);

        CREATE TABLE filings (
          id bigserial PRIMARY KEY,
          security_id integer NOT NULL REFERENCES securities (id),
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          accession_number text NOT NULL,
          form text NOT NULL,
          filing_date date NOT NULL,
          report_date date,
          accepted_at timestamptz,
          document_url text NOT NULL,
          UNIQUE (security_id, accession_number)
        );

        CREATE TABLE economic_observations (
          id bigserial PRIMARY KEY,
          series_id text NOT NULL,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          observation_date date NOT NULL,
          realtime_start date NOT NULL,
          value double precision,
          UNIQUE (series_id, observation_date, realtime_start)
        );

        CREATE TABLE validation_issues (
          id bigserial PRIMARY KEY,
          feed text NOT NULL,
          kind text NOT NULL CHECK (kind IN ('invalid', 'outlier', 'gap', 'missing', 'conflict')),
          ticker text,
          market_date date,
          detail text NOT NULL,
          detected_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX ix_validation_issues_detected ON validation_issues (detected_at DESC);

        CREATE FUNCTION reject_change() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in APPEND_ONLY:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_change()"
        )


def downgrade() -> None:
    for table in (
        "validation_issues",
        "economic_observations",
        "filings",
        "price_bars",
        "fetches",
        "feed_runs",
        "securities",
    ):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION reject_change")
    op.execute("DELETE FROM data_sources WHERE name IN ('SEC EDGAR', 'FRED', 'Tiingo')")
