from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_lab.db.models import Run, RunLease
from agentic_lab.domain.enums import RunStatus
from agentic_lab.runs.service import transition_run


def claim_next_run(session: Session, worker_id: str, lease_seconds: int) -> Run | None:
    now = datetime.now(UTC)
    run = session.scalars(
        select(Run)
        .where(Run.status == RunStatus.QUEUED)
        .order_by(Run.created_at)
        .with_for_update(skip_locked=True)
    ).first()
    if run is not None:
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", worker_id)
        session.add(_new_lease(run.id, worker_id, now, lease_seconds, 1))
        return run

    lease = session.scalars(
        select(RunLease)
        .where(RunLease.expires_at < now.replace(tzinfo=None))
        .order_by(RunLease.expires_at)
        .with_for_update(skip_locked=True)
    ).first()
    if lease is None:
        return None
    run = session.get(Run, lease.run_id)
    if run is None or run.status != RunStatus.LEASED:
        return None
    lease.worker_id = worker_id
    lease.acquired_at = now
    lease.heartbeat_at = now
    lease.expires_at = now + timedelta(seconds=lease_seconds)
    lease.attempt += 1
    return run


def heartbeat_lease(session: Session, run_id: object, worker_id: str, lease_seconds: int) -> bool:
    lease = session.get(RunLease, run_id)
    if lease is None or lease.worker_id != worker_id:
        return False
    now = datetime.now(UTC)
    expires_at = lease.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at < now:
        return False
    lease.heartbeat_at = now
    lease.expires_at = now + timedelta(seconds=lease_seconds)
    return True


def release_lease(session: Session, run_id: UUID, worker_id: str) -> bool:
    lease = session.get(RunLease, run_id)
    if lease is None or lease.worker_id != worker_id:
        return False
    session.delete(lease)
    return True


def _new_lease(
    run_id: object, worker_id: str, now: datetime, lease_seconds: int, attempt: int
) -> RunLease:
    return RunLease(
        run_id=run_id,
        worker_id=worker_id,
        acquired_at=now,
        heartbeat_at=now,
        expires_at=now + timedelta(seconds=lease_seconds),
        attempt=attempt,
    )
