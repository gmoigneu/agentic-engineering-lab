"""evaluation records, causal links, and run lookup indexes

Revision ID: 0005_evaluation_causal
Revises: 0004_manifest_opt_in
"""

from __future__ import annotations

from sqlalchemy import inspect

from agentic_lab.db.base import Base
from agentic_lab.db.models import Evaluation, RedactionEvent, RunCausalLink, WebhookRunLink
from alembic import op

revision = "0005_evaluation_causal"
down_revision = "0004_manifest_opt_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind,
        tables=[
            Evaluation.__table__,
            RunCausalLink.__table__,
            RedactionEvent.__table__,
            WebhookRunLink.__table__,
        ],
    )
    existing = {item["name"] for item in inspect(bind).get_indexes("runs")}
    if "ix_runs_repository_sha" not in existing:
        op.create_index("ix_runs_repository_sha", "runs", ["repository_id", "pinned_sha"])
    if "ix_runs_pull_sha" not in existing:
        op.create_index("ix_runs_pull_sha", "runs", ["pull_number", "pinned_sha"])


def downgrade() -> None:
    existing = {item["name"] for item in inspect(op.get_bind()).get_indexes("runs")}
    if "ix_runs_pull_sha" in existing:
        op.drop_index("ix_runs_pull_sha", table_name="runs")
    if "ix_runs_repository_sha" in existing:
        op.drop_index("ix_runs_repository_sha", table_name="runs")
    Base.metadata.drop_all(
        op.get_bind(),
        tables=[
            WebhookRunLink.__table__,
            RedactionEvent.__table__,
            RunCausalLink.__table__,
            Evaluation.__table__,
        ],
    )
