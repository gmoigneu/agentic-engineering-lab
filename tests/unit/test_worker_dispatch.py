from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import RunLease
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.leases import claim_next_run
from agentic_lab.runs.service import create_queued_run, transition_run
from agentic_lab.runs.worker import WorkerDependencies, dispatch_run, process_claimed_run


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


def test_claimed_run_is_processed_under_lease_and_released():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
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
        run_id = run.id
    with sessions.begin() as session:
        assert claim_next_run(session, "worker", 10) is not None

    assert process_claimed_run(
        sessions, run_id, "worker", 10, WorkerDependencies(None, None)
    )

    with sessions() as session:
        processed = session.get(type(run), run_id)
        assert processed is not None
        assert processed.status is RunStatus.FAILED
        assert session.get(RunLease, run_id) is None
