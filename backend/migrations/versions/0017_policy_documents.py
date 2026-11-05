"""US government policy actions from the Federal Register.

Revision ID: 0017
Revises: 0016
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO data_sources (name, trust_rank, base_url)
        VALUES ('Federal Register', 1, 'https://www.federalregister.gov');
        CREATE TABLE policy_documents (
          document_number text PRIMARY KEY,
          fetch_id bigint NOT NULL REFERENCES fetches (id),
          kind text NOT NULL,
          title text NOT NULL,
          published date NOT NULL,
          topic text,
          url text NOT NULL
        );
        CREATE INDEX policy_documents_latest ON policy_documents (published DESC);
        CREATE TRIGGER policy_documents_append_only BEFORE UPDATE OR DELETE ON policy_documents
          FOR EACH ROW EXECUTE FUNCTION reject_change();
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE policy_documents;
        DELETE FROM data_sources WHERE name = 'Federal Register';
        """
    )
