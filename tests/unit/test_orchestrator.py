from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import Citation, Claim, RunCreate, ScoutArtifact
from agentic_lab.gateway.model import ScriptedModelGateway
from agentic_lab.runs.orchestrator import orchestrate_scout
from agentic_lab.runs.service import create_queued_run, transition_run


def test_orchestrator_stores_valid_scout_artifact() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(role=AgentRole.SCOUT, repository_id=1, pinned_sha="a" * 40, task_text="map"),
            RunSource.MANUAL,
            "operator",
        )
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
        artifact = ScoutArtifact(
            run_id=run.id,
            role=AgentRole.SCOUT,
            pinned_sha="a" * 40,
            claims=[Claim(id="c", statement="evidence")],
            citations=[
                Citation(
                    claim_id="c",
                    source_kind="file",
                    locator="a.py#L1-L1",
                    pinned_sha="a" * 40,
                    excerpt_hash="b" * 64,
                )
            ],
            relevant_files=[],
            dependency_analysis="none",
            blast_radius="none",
            plan=[],
            confidence=1,
        )
        orchestrate_scout(session, run, ScriptedModelGateway(artifact), "model@1")
        assert run.status is RunStatus.SUCCEEDED
