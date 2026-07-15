from __future__ import annotations

from dataclasses import dataclass

from agentic_lab.domain.schemas import ArtifactBase, RiskArtifact


@dataclass(frozen=True)
class EvaluationResult:
    name: str
    passed: bool
    detail: str


def citation_coverage(artifact: ArtifactBase) -> EvaluationResult:
    cited = {citation.claim_id for citation in artifact.citations}
    missing = [claim.id for claim in artifact.claims if claim.material and claim.id not in cited]
    return EvaluationResult("citation_coverage", not missing, ",".join(missing) or "complete")


def risk_evidence_coverage(artifact: RiskArtifact) -> EvaluationResult:
    result = citation_coverage(artifact)
    if not artifact.claims:
        return EvaluationResult("risk_evidence_coverage", False, "risk output has no evidence claims")
    return EvaluationResult("risk_evidence_coverage", result.passed, result.detail)
