from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.service import create_queued_run, transition_run
from agentic_lab.runs.worker import WorkerDependencies, dispatch_run


def test_unconfigured_role_is_terminal_and_auditable():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        with session.begin():
            run = create_queued_run(
                session,
                RunCreate(
                    role=AgentRole.ASSESSOR,
                    repository_id=1,
                    pinned_sha="a" * 40,
                    task_text="assess",
                ),
                RunSource.MANUAL,
                "operator",
            )
            transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
            dispatch_run(session, run, "worker", WorkerDependencies(None, None))
            assert run.status is RunStatus.FAILED
