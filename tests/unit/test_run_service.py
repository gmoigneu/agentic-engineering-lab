from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import RunTransition
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.service import InvalidTransitionError, create_queued_run, transition_run


def test_run_records_intake_and_queue_transitions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.SCOUT,
                repository_id=123456,
                pinned_sha="a" * 40,
                task_text="Map the change.",
            ),
            RunSource.MANUAL,
            "operator",
        )
        assert run.status is RunStatus.QUEUED
        transitions = list(
            session.query(RunTransition)
            .filter_by(run_id=run.id)
            .order_by(RunTransition.occurred_at)
        )
        assert [item.to_status for item in transitions] == [RunStatus.RECEIVED, RunStatus.QUEUED]


def test_terminal_transition_is_immutable() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.SCOUT,
                repository_id=123456,
                pinned_sha="a" * 40,
                task_text="Map the change.",
            ),
            RunSource.MANUAL,
            "operator",
        )
        transition_run(session, run, RunStatus.CANCELLED, "operator_cancelled", "operator")
        try:
            transition_run(session, run, RunStatus.QUEUED, "invalid", "operator")
        except InvalidTransitionError:
            pass
        else:
            raise AssertionError("terminal run accepted another transition")
