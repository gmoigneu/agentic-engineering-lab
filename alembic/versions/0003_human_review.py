"""human review records

Revision ID: 0003_human_review
Revises: 0002_scout_observability
"""

from agentic_lab.db.base import Base
from agentic_lab.db.models import HumanReview
from alembic import op

revision = "0003_human_review"
down_revision = "0002_scout_observability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind(), tables=[HumanReview.__table__])


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind(), tables=[HumanReview.__table__])
