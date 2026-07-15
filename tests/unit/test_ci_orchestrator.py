from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.orchestrator import refuse_ci_failure
from agentic_lab.runs.service import create_queued_run, transition_run


def test_ci_external_failure_refuses_before_execution():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        with session.begin():
            run = create_queued_run(
                session,
                RunCreate(role=AgentRole.CI, repository_id=1, pinned_sha="a" * 40, task_text="fix"),
                RunSource.MANUAL,
                "operator",
            )
            transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
            refuse_ci_failure(session, run, "network timeout")
            assert run.status is RunStatus.REFUSED
