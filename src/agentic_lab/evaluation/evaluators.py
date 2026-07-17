from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from agentic_lab.domain.schemas import ArtifactBase, RiskArtifact, ScoutArtifact
from agentic_lab.tools.snapshot import RepositorySnapshot


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
        return EvaluationResult(
            "risk_evidence_coverage", False, "risk output has no evidence claims"
        )
    return EvaluationResult("risk_evidence_coverage", result.passed, result.detail)


def citation_resolution(artifact: ArtifactBase, snapshot: RepositorySnapshot) -> EvaluationResult:
    unresolved: list[str] = []
    pattern = re.compile(r"^(.+)#L(\d+)-L(\d+)$")
    for citation in artifact.citations:
        if citation.pinned_sha != snapshot.pinned_sha:
            unresolved.append(citation.locator)
            continue
        match = pattern.fullmatch(citation.locator)
        if match is None:
            if citation.source_kind not in {"commit", "diff", "check_run", "tool_result"}:
                unresolved.append(citation.locator)
            continue
        path, start, end = match.groups()
        try:
            result = snapshot.read_file(path, int(start), int(end))
        except (FileNotFoundError, ValueError):
            unresolved.append(citation.locator)
            continue
        if (
            not result.text
            or hashlib.sha256(result.text.encode()).hexdigest() != citation.excerpt_hash
        ):
            unresolved.append(citation.locator)
    return EvaluationResult(
        "citation_resolution", not unresolved, ",".join(unresolved) or "complete"
    )


def scout_relevant_file_recall(
    artifact: ScoutArtifact, expected_paths: set[str]
) -> EvaluationResult:
    actual = {item.path for item in artifact.relevant_files}
    if not expected_paths:
        return EvaluationResult("relevant_file_recall", False, "fixture has no expected paths")
    recall = len(actual & expected_paths) / len(expected_paths)
    return EvaluationResult("relevant_file_recall", recall == 1.0, f"{recall:.3f}")


def tool_permission_compliance(
    requested_tools: list[str], allowed_tools: frozenset[str]
) -> EvaluationResult:
    denied = sorted(set(requested_tools) - allowed_tools)
    return EvaluationResult(
        "tool_permission_compliance", not denied, ",".join(denied) or "complete"
    )
