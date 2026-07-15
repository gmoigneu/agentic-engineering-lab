"""lab foundation

Revision ID: 0001_lab_foundation
Revises:
Create Date: 2026-07-15
"""

from __future__ import annotations

from agentic_lab.db.base import Base
from agentic_lab.db.models import Run, RunLease, RunTransition, WebhookEvent
from alembic import op

revision = "0001_lab_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(
        bind,
        tables=[WebhookEvent.__table__, Run.__table__, RunTransition.__table__, RunLease.__table__],
    )


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(
        bind,
        tables=[RunLease.__table__, RunTransition.__table__, Run.__table__, WebhookEvent.__table__],
    )
