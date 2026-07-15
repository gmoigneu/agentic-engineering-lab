from uuid import uuid4

from agentic_lab.agents.scout import run_scout
from agentic_lab.domain.enums import AgentRole
from agentic_lab.domain.schemas import Citation, Claim, ScoutArtifact
from agentic_lab.gateway.model import ModelBudget, ScriptedModelGateway


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
        citations=[Citation(claim_id="one", source_kind="file", locator="a.py#L1-L1", pinned_sha="a" * 40, excerpt_hash="b" * 64)],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=0.5,
    )
    assert run_scout(ScriptedModelGateway(artifact), run_id, "a" * 40, "map", "model@1", ModelBudget(1, 1, 1)) == artifact
