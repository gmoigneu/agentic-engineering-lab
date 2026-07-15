from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import PolicyDecision
from agentic_lab.domain.enums import AgentRole, RunSource
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.policy.audit import record_decision
from agentic_lab.policy.patch import PatchPolicy, validate_unified_diff
from agentic_lab.runs.service import create_queued_run


def test_policy_decisions_are_durable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        with session.begin():
            run = create_queued_run(
                session,
                RunCreate(
                    role=AgentRole.SCOUT, repository_id=1, pinned_sha="a" * 40, task_text="map"
                ),
                RunSource.MANUAL,
                "operator",
            )
            record_decision(
                session,
                run.id,
                "patch",
                validate_unified_diff("+++ b/src/a.py\n+x", PatchPolicy(("src/**",), ())),
            )
        assert session.scalar(select(PolicyDecision)) is not None
