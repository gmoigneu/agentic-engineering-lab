"""persist check-run identity for typed evidence retrieval

Revision ID: 0006_check_evidence
Revises: 0005_evaluation_causal
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_check_evidence"
down_revision = "0005_evaluation_causal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns("runs")}
    if "check_run_id" not in columns:
        op.add_column("runs", sa.Column("check_run_id", sa.BigInteger(), nullable=True))
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("runs")}
    if "ix_runs_check_run_id" not in indexes:
        op.create_index("ix_runs_check_run_id", "runs", ["check_run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("runs")}
    if "ix_runs_check_run_id" in indexes:
        op.drop_index("ix_runs_check_run_id", table_name="runs")
    columns = {item["name"] for item in sa.inspect(bind).get_columns("runs")}
    if "check_run_id" in columns:
        op.drop_column("runs", "check_run_id")
