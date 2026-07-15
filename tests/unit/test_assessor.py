from uuid import uuid4

from agentic_lab.agents.assessor import run_assessor
from agentic_lab.domain.enums import AgentRole
from agentic_lab.domain.schemas import Citation, Claim, RiskArtifact
from agentic_lab.gateway.model import ModelBudget, ScriptedModelGateway


def test_assessor_requires_evidence_coverage() -> None:
    run_id = uuid4()
    artifact = RiskArtifact(
        run_id=run_id,
        role=AgentRole.ASSESSOR,
        pinned_sha="a" * 40,
        claims=[Claim(id="risk", statement="risk")],
        citations=[
            Citation(
                claim_id="risk",
                source_kind="diff",
                locator="diff#a",
                pinned_sha="a" * 40,
                excerpt_hash="b" * 64,
            )
        ],
        risk_tier="high",
        confidence=0.8,
        likely_failure_modes=["regression"],
        required_proof=["test"],
        reviewer_expertise=["backend"],
    )
    assert (
        run_assessor(
            ScriptedModelGateway(artifact),
            run_id,
            "a" * 40,
            "assess",
            "model@1",
            ModelBudget(1, 1, 1),
        )
        == artifact
    )
