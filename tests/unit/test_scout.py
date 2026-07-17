import hashlib
from uuid import uuid4

from agentic_lab.agents.scout import run_scout
from agentic_lab.domain.enums import AgentRole
from agentic_lab.domain.schemas import Citation, Claim, ScoutArtifact
from agentic_lab.gateway.model import ModelBudget, ScriptedModelGateway
from agentic_lab.tools.registry import SnapshotToolRegistry
from agentic_lab.tools.snapshot import RepositorySnapshot


def test_scout_rejects_uncited_material_claim() -> None:
    run_id = uuid4()
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha="a" * 40,
        claims=[Claim(id="one", statement="claim")],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=0.5,
    )
    gateway = ScriptedModelGateway(artifact)
    try:
        run_scout(gateway, run_id, "a" * 40, "map", "model@1", ModelBudget(1, 1, 1))
    except ValueError as error:
        assert "unsupported" in str(error)
    else:
        raise AssertionError("uncited scout claim was accepted")


def test_scout_accepts_cited_output() -> None:
    run_id = uuid4()
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha="a" * 40,
        claims=[Claim(id="one", statement="claim")],
        citations=[
            Citation(
                claim_id="one",
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
        confidence=0.5,
    )
    assert (
        run_scout(
            ScriptedModelGateway(artifact), run_id, "a" * 40, "map", "model@1", ModelBudget(1, 1, 1)
        )
        == artifact
    )


def test_scout_supplies_durable_identity_and_bounded_evidence_strategy() -> None:
    run_id = uuid4()
    pinned_sha = "a" * 40
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha=pinned_sha,
        relevant_files=[],
        dependency_analysis="unknown",
        blast_radius="unknown",
        plan=[],
        confidence=0,
    )
    gateway = ScriptedModelGateway(artifact)

    run_scout(gateway, run_id, pinned_sha, "map", "model@1", ModelBudget(12, 40, 1))

    request_task = gateway.requests[0].task
    assert str(run_id) in request_task
    assert pinned_sha in request_task
    assert "no more than 20 tool calls" in request_task.lower()
    assert "no more than 8 evidence rounds" in request_task.lower()
    assert "reserve the final model turn" in request_task.lower()
    assert "do not fabricate" in request_task.lower()


def test_scout_canonicalizes_and_resolves_model_citations() -> None:
    run_id = uuid4()
    pinned_sha = "a" * 40
    excerpt_hash = hashlib.sha256(b"claim").hexdigest()
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha=pinned_sha,
        claims=[Claim(id="one", statement="claim")],
        citations=[
            Citation(
                claim_id="one",
                source_kind="file",
                locator="a.py",
                pinned_sha=pinned_sha,
                excerpt_hash=excerpt_hash,
            )
        ],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=1,
    )
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot(pinned_sha, {"a.py": "claim\n"}),
        max_calls=40,
    )

    class EvidenceGateway(ScriptedModelGateway[ScoutArtifact]):
        def run_agent_loop(self, request, output_type):  # type: ignore[no-untyped-def]
            assert request.tools is not None
            request.tools.execute(
                "read_file", {"path": "a.py", "start_line": 1, "end_line": 1}
            )
            return super().run_agent_loop(request, output_type)

    result = run_scout(
        EvidenceGateway(artifact),
        run_id,
        pinned_sha,
        "map",
        "model@1",
        ModelBudget(12, 40, 1),
        tools,
    )

    assert result.citations[0].locator == "a.py#L1-L1"


def test_scout_rejects_citations_not_returned_by_its_tools() -> None:
    run_id = uuid4()
    pinned_sha = "a" * 40
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha=pinned_sha,
        claims=[Claim(id="one", statement="claim")],
        citations=[
            Citation(
                claim_id="one",
                source_kind="file",
                locator="invented.py#L1-L1",
                pinned_sha=pinned_sha,
                excerpt_hash="b" * 64,
            )
        ],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=1,
    )
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot(pinned_sha, {"a.py": "claim\n"}),
        max_calls=40,
    )

    try:
        run_scout(
            ScriptedModelGateway(artifact),
            run_id,
            pinned_sha,
            "map",
            "model@1",
            ModelBudget(12, 40, 1),
            tools,
        )
    except ValueError as error:
        assert "unresolved citations" in str(error)
    else:
        raise AssertionError("unresolved citation was accepted")


def test_scout_discards_extra_unresolved_citation_when_claim_remains_supported() -> None:
    run_id = uuid4()
    pinned_sha = "a" * 40
    excerpt_hash = hashlib.sha256(b"claim").hexdigest()
    artifact = ScoutArtifact(
        run_id=run_id,
        role=AgentRole.SCOUT,
        pinned_sha=pinned_sha,
        claims=[Claim(id="one", statement="claim")],
        citations=[
            Citation(
                claim_id="one",
                source_kind="file",
                locator="invented-search-description",
                pinned_sha=pinned_sha,
                excerpt_hash="b" * 64,
            ),
            Citation(
                claim_id="one",
                source_kind="file",
                locator="a.py",
                pinned_sha=pinned_sha,
                excerpt_hash=excerpt_hash,
            ),
        ],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=1,
    )
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot(pinned_sha, {"a.py": "claim\n"}),
        max_calls=40,
    )

    class EvidenceGateway(ScriptedModelGateway[ScoutArtifact]):
        def run_agent_loop(self, request, output_type):  # type: ignore[no-untyped-def]
            assert request.tools is not None
            request.tools.execute(
                "read_file", {"path": "a.py", "start_line": 1, "end_line": 1}
            )
            return super().run_agent_loop(request, output_type)

    result = run_scout(
        EvidenceGateway(artifact),
        run_id,
        pinned_sha,
        "map",
        "model@1",
        ModelBudget(12, 40, 1),
        tools,
    )

    assert [citation.locator for citation in result.citations] == ["a.py#L1-L1"]
