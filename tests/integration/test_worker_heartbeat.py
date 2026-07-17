from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import RunLease
from agentic_lab.domain.enums import AgentRole, RunSource
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.heartbeat import LeaseHeartbeat, LeaseLostError
from agentic_lab.runs.leases import claim_next_run
from agentic_lab.runs.service import create_queued_run


def _sessions(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'heartbeat.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _claimed_run(sessions):
    with sessions.begin() as session:
        created = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.SCOUT,
                repository_id=1,
                pinned_sha="a" * 40,
                task_text="map",
            ),
            RunSource.MANUAL,
            "operator",
        )
        run_id = created.id
    with sessions.begin() as session:
        assert claim_next_run(session, "worker-a", 10) is not None
    return run_id


def test_heartbeat_renews_lease_during_long_work(tmp_path) -> None:
    sessions = _sessions(tmp_path)
    run_id = _claimed_run(sessions)
    with sessions() as session:
        original = session.get(RunLease, run_id)
        assert original is not None
        original_heartbeat = original.heartbeat_at

    heartbeat = LeaseHeartbeat(
        sessions, run_id, "worker-a", lease_seconds=10, interval_seconds=0.01
    )
    with heartbeat:
        assert heartbeat.wait_until_renewed(timeout=1)

    with sessions() as session:
        renewed = session.get(RunLease, run_id)
        assert renewed is not None
        assert renewed.heartbeat_at > original_heartbeat
        assert renewed.expires_at > renewed.heartbeat_at
    assert not heartbeat.is_alive


def test_heartbeat_reports_lease_ownership_loss(tmp_path) -> None:
    sessions = _sessions(tmp_path)
    run_id = _claimed_run(sessions)
    heartbeat = LeaseHeartbeat(
        sessions, run_id, "worker-a", lease_seconds=10, interval_seconds=0.01
    )

    try:
        with heartbeat:
            with sessions.begin() as session:
                lease = session.get(RunLease, run_id)
                assert lease is not None
                lease.worker_id = "worker-b"
            assert heartbeat.wait_until_lost(timeout=1)
    except LeaseLostError:
        pass
    else:
        raise AssertionError("lease ownership loss must be terminal for the worker attempt")
