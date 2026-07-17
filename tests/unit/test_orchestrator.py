from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import Artifact, ModelCall, RedactionEvent, ToolCall
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import Citation, Claim, RiskArtifact, RunCreate, ScoutArtifact
from agentic_lab.gateway.capability import CapabilityGateway
from agentic_lab.gateway.github_read import Archive, PinnedArchiveReader
from agentic_lab.gateway.model import ModelCallMetadata, ModelGatewayError, ScriptedModelGateway
from agentic_lab.gateway.tracing import TraceExporter, trace_id_for_run
from agentic_lab.runs.orchestrator import orchestrate_assessor, orchestrate_scout
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


def test_orchestrator_persists_safe_model_gateway_details() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    class FailingGateway:
        last_call = None
        last_provider_allowlist = ("StreamLake",)

        def run_agent_loop(self, request, output_type):  # type: ignore[no-untyped-def]
            raise ModelGatewayError(
                "provider HTTP 429; code=429; message=Provider rate limit reached"
            )

    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(role=AgentRole.SCOUT, repository_id=1, pinned_sha="a" * 40, task_text="map"),
            RunSource.MANUAL,
            "operator",
        )
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")

        orchestrate_scout(session, run, FailingGateway(), "model@1")

        terminal_error = session.scalar(select(Artifact).where(Artifact.run_id == run.id))
        assert terminal_error is not None
        assert run.status is RunStatus.FAILED
        assert terminal_error.content_json["message"] == (
            "provider HTTP 429; code=429; message=Provider rate limit reached"
        )


def test_orchestrator_correlates_redacted_model_trace_to_run() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    class Sink:
        payload = None

        def emit(self, trace_id, name, payload):  # type: ignore[no-untyped-def]
            self.payload = (trace_id, name, payload)

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
            relevant_files=[],
            dependency_analysis="none",
            blast_radius="none",
            plan=[],
            confidence=1,
        )
        sink = Sink()
        gateway = ScriptedModelGateway(artifact)
        gateway.last_call = ModelCallMetadata(
            "StreamLake", {"input_tokens": 12, "output_tokens": 4}, 0.01
        )
        gateway.trace_exporter = TraceExporter(sink)

        orchestrate_scout(session, run, gateway, "model@1")

        model_call = session.scalar(select(ModelCall).where(ModelCall.run_id == run.id))
        assert model_call is not None
        assert model_call.langfuse_trace_id == trace_id_for_run(str(run.id))
        assert sink.payload is not None
        assert sink.payload[2]["run_id"] == str(run.id)
        assert "map" not in sink.payload[2]["text"]


def test_orchestrator_records_trace_redaction_block_without_export() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    class Sink:
        emitted = False

        def emit(self, trace_id, name, payload):  # type: ignore[no-untyped-def]
            self.emitted = True

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
            relevant_files=[],
            dependency_analysis="none",
            blast_radius="none",
            plan=[],
            confidence=1,
        )
        sink = Sink()
        gateway = ScriptedModelGateway(artifact)
        gateway.last_call = ModelCallMetadata("ghp_" + "a" * 36, {}, 0)
        gateway.trace_exporter = TraceExporter(sink)

        orchestrate_scout(session, run, gateway, "model@1")

        model_call = session.scalar(select(ModelCall).where(ModelCall.run_id == run.id))
        redaction = session.scalar(
            select(RedactionEvent).where(RedactionEvent.run_id == run.id)
        )
        assert model_call is not None
        assert model_call.langfuse_trace_id is None
        assert redaction is not None
        assert redaction.source_locator == "trace:model-call"
        assert not sink.emitted


def test_assessor_receives_audited_snapshot_tools() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    pinned_sha = "a" * 40

    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.ASSESSOR,
                repository_id=1,
                pinned_sha=pinned_sha,
                task_text="assess",
            ),
            RunSource.MANUAL,
            "operator",
        )
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
        artifact = RiskArtifact(
            run_id=run.id,
            role=AgentRole.ASSESSOR,
            pinned_sha=pinned_sha,
            claims=[Claim(id="risk", statement="configuration change")],
            citations=[
                Citation(
                    claim_id="risk",
                    source_kind="file",
                    locator="src/config.py#L1-L1",
                    pinned_sha=pinned_sha,
                    excerpt_hash="b" * 64,
                )
            ],
            risk_tier="medium",
            confidence=0.8,
            likely_failure_modes=["configuration regression"],
            required_proof=["configuration test"],
            reviewer_expertise=["backend"],
        )

        class EvidenceGateway(ScriptedModelGateway[RiskArtifact]):
            def run_agent_loop(self, request, output_type):  # type: ignore[no-untyped-def]
                assert request.tools is not None
                request.tools.execute(
                    "read_file",
                    {"path": "src/config.py", "start_line": 1, "end_line": 1},
                )
                return super().run_agent_loop(request, output_type)

        capability = CapabilityGateway(
            PinnedArchiveReader(
                {(1, pinned_sha): Archive(1, pinned_sha, {"src/config.py": "SETTING = 1\n"})}
            ),
            frozenset({1}),
        )

        orchestrate_assessor(session, run, EvidenceGateway(artifact), "model@1", capability)

        assert run.status is RunStatus.SUCCEEDED
        assert session.query(ToolCall).filter_by(run_id=run.id).count() == 1
