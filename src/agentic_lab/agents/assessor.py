from agentic_lab.domain.schemas import RiskArtifact
from agentic_lab.evaluation.evaluators import risk_evidence_coverage


def validate_risk_artifact(artifact: RiskArtifact) -> RiskArtifact:
    result = risk_evidence_coverage(artifact)
    if not result.passed:
        raise ValueError(f"invalid risk output: {result.detail}")
    return artifact
