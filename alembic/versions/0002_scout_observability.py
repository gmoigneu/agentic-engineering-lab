"""scout artifacts and observability

Revision ID: 0002_scout_observability
Revises: 0001_lab_foundation
"""

from __future__ import annotations

from agentic_lab.db.base import Base
from agentic_lab.db.models import Artifact, CitationRecord, ModelCall, PolicyDecision, ToolCall
from alembic import op

revision = "0002_scout_observability"
down_revision = "0001_lab_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(
        op.get_bind(),
        tables=[
            Artifact.__table__,
            CitationRecord.__table__,
            PolicyDecision.__table__,
            ToolCall.__table__,
            ModelCall.__table__,
        ],
    )


def downgrade() -> None:
    Base.metadata.drop_all(
        op.get_bind(),
        tables=[
            ModelCall.__table__,
            ToolCall.__table__,
            PolicyDecision.__table__,
            CitationRecord.__table__,
            Artifact.__table__,
        ],
    )
