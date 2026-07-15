from agentic_lab.domain.schemas import CIDiagnosisArtifact, RefusalArtifact

_REFUSAL_CLASSES = frozenset({"external", "flaky", "permission", "secret", "infrastructure"})


def requires_refusal(artifact: CIDiagnosisArtifact) -> bool:
    return artifact.failure_class in _REFUSAL_CLASSES


def build_refusal(
    artifact: CIDiagnosisArtifact, missing_precondition: str, next_action: str
) -> RefusalArtifact:
    if not requires_refusal(artifact):
        raise ValueError(
            "repository-caused failure requires deterministic validation before refusal"
        )
    return RefusalArtifact(
        run_id=artifact.run_id,
        role=artifact.role,
        pinned_sha=artifact.pinned_sha,
        claims=artifact.claims,
        unknowns=artifact.unknowns,
        citations=artifact.citations,
        failure_class=artifact.failure_class,
        missing_precondition=missing_precondition,
        next_action=next_action,
    )
