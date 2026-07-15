"""lab-owned manifests and pull request opt-ins

Revision ID: 0004_manifest_opt_in
Revises: 0003_human_review
"""

from agentic_lab.db.base import Base
from agentic_lab.db.models import PullRequestOptIn, TargetManifest
from alembic import op

revision = "0004_manifest_opt_in"
down_revision = "0003_human_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(
        op.get_bind(), tables=[TargetManifest.__table__, PullRequestOptIn.__table__]
    )


def downgrade() -> None:
    Base.metadata.drop_all(
        op.get_bind(), tables=[PullRequestOptIn.__table__, TargetManifest.__table__]
    )
