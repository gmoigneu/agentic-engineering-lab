from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_lab.db.models import Run, RunCausalLink, RunTransition
from agentic_lab.domain.enums import ALLOWED_TRANSITIONS, TERMINAL_STATUSES, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate


class InvalidTransitionError(ValueError):
    pass


class RunNotFoundError(LookupError):
    pass


def create_queued_run(session: Session, data: RunCreate, source: RunSource, actor: str) -> Run:
    run = Run(
        role=data.role,
        source=source,
        repository_id=data.repository_id,
        pinned_sha=data.pinned_sha,
        task_text=data.task_text,
        status=RunStatus.RECEIVED,
        manifest_version="unselected",
        policy_version="v1",
        budget=data.budget,
        evaluation_case_id=data.evaluation_case_id,
    )
    session.add(run)
    session.flush()
    _record_transition(session, run, None, RunStatus.RECEIVED, "intake_received", actor)
    transition_run(session, run, RunStatus.QUEUED, "intake_accepted", actor)
    return run


def link_runs(session: Session, source: Run, target: Run, relation: str) -> RunCausalLink:
    if source.id == target.id:
        raise ValueError("a run cannot be causally linked to itself")
    link = RunCausalLink(source_run_id=source.id, target_run_id=target.id, relation=relation)
    session.add(link)
    return link


def supersede_active_runs(
    session: Session,
    repository_id: int,
    pull_number: int,
    newer_sha: str,
    actor: str,
) -> list[Run]:
    active_statuses = set(ALLOWED_TRANSITIONS) - TERMINAL_STATUSES
    candidates = list(
        session.scalars(
            select(Run).where(
                Run.repository_id == repository_id,
                Run.pull_number == pull_number,
                Run.pinned_sha != newer_sha,
                Run.status.in_(active_statuses),
            )
        )
    )
    superseded: list[Run] = []
    for candidate in candidates:
        if RunStatus.SUPERSEDED in ALLOWED_TRANSITIONS.get(candidate.status, frozenset()):
            transition_run(
                session,
                candidate,
                RunStatus.SUPERSEDED,
                "newer_human_head_sha",
                actor,
                {"replacement_sha": newer_sha},
            )
            superseded.append(candidate)
    return superseded


def transition_run(
    session: Session,
    run: Run,
    target: RunStatus,
    reason_code: str,
    actor: str,
    metadata: dict[str, object] | None = None,
) -> None:
    if target not in ALLOWED_TRANSITIONS.get(run.status, frozenset()):
        raise InvalidTransitionError(f"{run.status} cannot transition to {target}")
    previous = run.status
    run.status = target
    if target in TERMINAL_STATUSES:
        run.terminal_at = datetime.now(UTC)
    _record_transition(session, run, previous, target, reason_code, actor, metadata)


def get_run(session: Session, run_id: UUID) -> Run:
    run = session.get(Run, run_id)
    if run is None:
        raise RunNotFoundError(str(run_id))
    return run


def list_transitions(session: Session, run_id: UUID) -> list[RunTransition]:
    return list(
        session.scalars(
            select(RunTransition)
            .where(RunTransition.run_id == run_id)
            .order_by(RunTransition.occurred_at, RunTransition.id)
        )
    )


def _record_transition(
    session: Session,
    run: Run,
    source: RunStatus | None,
    target: RunStatus,
    reason_code: str,
    actor: str,
    metadata: dict[str, object] | None = None,
) -> None:
    session.add(
        RunTransition(
            run_id=run.id,
            from_status=source,
            to_status=target,
            reason_code=reason_code,
            actor=actor,
            metadata_json=metadata or {},
        )
    )
