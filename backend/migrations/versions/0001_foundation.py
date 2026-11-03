"""Foundation tables: data sources and worker heartbeats.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("trust_rank", sa.Integer, nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("trust_rank BETWEEN 1 AND 4", name="ck_data_sources_trust_rank"),
    )
    op.create_table(
        "worker_heartbeats",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column(
            "beat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_worker_heartbeats_beat_at", "worker_heartbeats", ["beat_at"])


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
    op.drop_table("data_sources")
