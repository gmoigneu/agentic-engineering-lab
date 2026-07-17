from uuid import uuid4

from agentic_lab.domain.enums import AgentRole
from agentic_lab.domain.schemas import Claim, ScoutArtifact
from agentic_lab.evaluation.evaluators import citation_coverage


def test_material_claim_requires_resolvable_citation() -> None:
    artifact = ScoutArtifact.model_construct(
        run_id=uuid4(),
        role=AgentRole.SCOUT,
        pinned_sha="a" * 40,
        claims=[Claim(id="claim-1", statement="A material statement")],
        relevant_files=[],
        dependency_analysis="none",
        blast_radius="none",
        plan=[],
        confidence=0.5,
    )
    assert not citation_coverage(artifact).passed
