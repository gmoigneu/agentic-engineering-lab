from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus


class RunCreate(BaseModel):
    role: AgentRole
    repository_id: int = Field(gt=0)
    pinned_sha: str = Field(min_length=40, max_length=64)
    task_text: str = Field(min_length=1, max_length=20_000)
    evaluation_case_id: str | None = Field(default=None, max_length=255)
    budget: dict[str, int | float] = Field(default_factory=dict)

    @field_validator("pinned_sha")
    @classmethod
    def immutable_sha(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("pinned_sha must be a lowercase immutable Git SHA")
        return value


class RunSummary(BaseModel):
    id: UUID
    role: AgentRole
    source: RunSource
    repository_id: int
    pinned_sha: str
    status: RunStatus
    created_at: datetime
    terminal_at: datetime | None = None
    manifest_version: str
    policy_version: str


class RunTransitionSummary(BaseModel):
    from_status: RunStatus | None
    to_status: RunStatus
    reason_code: str
    actor: str
    occurred_at: datetime


class RunDetail(RunSummary):
    request_id: UUID | None = None
    transitions: list[RunTransitionSummary]
    artifacts: list[str] = Field(default_factory=list)
    langfuse_trace_id: str | None = None
    event_delivery_id: str | None = None


class RunCreateResponse(BaseModel):
    request_id: UUID
    run: RunSummary


class WebhookResponse(BaseModel):
    request_id: UUID
    accepted: bool
    duplicate: bool = False
    run_id: UUID | None = None


class GithubReplay(BaseModel):
    """A stored signed fixture replayed through the same verification path."""

    delivery_id: str = Field(min_length=1, max_length=255)
    event_name: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1)
    signature: str = Field(min_length=8, max_length=255)


class Citation(BaseModel):
    claim_id: str = Field(min_length=1, max_length=100)
    source_kind: str = Field(min_length=1, max_length=100)
    locator: str = Field(min_length=1, max_length=2_000)
    pinned_sha: str = Field(min_length=40, max_length=64)
    excerpt_hash: str = Field(min_length=64, max_length=64)

    @field_validator("pinned_sha")
    @classmethod
    def immutable_citation_sha(cls, value: str) -> str:
        return _immutable_sha(value)

    @field_validator("excerpt_hash")
    @classmethod
    def hexadecimal_excerpt_hash(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("excerpt_hash must be lowercase hexadecimal")
        return value


class Claim(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1, max_length=10_000)
    material: bool = True


class ArtifactBase(BaseModel):
    schema_version: Literal["1"] = "1"
    run_id: UUID
    role: AgentRole
    pinned_sha: str = Field(min_length=40, max_length=64)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    claims: list[Claim] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    @field_validator("pinned_sha")
    @classmethod
    def immutable_artifact_sha(cls, value: str) -> str:
        return _immutable_sha(value)

    @model_validator(mode="after")
    def stable_claims_and_citations(self) -> ArtifactBase:
        claim_ids = [claim.id for claim in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim IDs must be unique")
        known_claims = set(claim_ids)
        if any(citation.claim_id not in known_claims for citation in self.citations):
            raise ValueError("citations must refer to a claim in the artifact")
        if any(citation.pinned_sha != self.pinned_sha for citation in self.citations):
            raise ValueError("citation SHA must match artifact SHA")
        return self


class EvidenceLocator(BaseModel):
    path: str
    symbol: str | None = None
    reason: str


class ScoutPlanStep(BaseModel):
    order: int = Field(ge=1)
    summary: str
    files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)


class ScoutArtifact(ArtifactBase):
    relevant_files: list[EvidenceLocator]
    relevant_symbols: list[EvidenceLocator] = Field(default_factory=list)
    dependency_analysis: str
    blast_radius: str
    affected_tests: list[str] = Field(default_factory=list)
    plan: list[ScoutPlanStep]
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def material_claims_have_citations(self) -> ScoutArtifact:
        material_claims = {claim.id for claim in self.claims if claim.material}
        cited_claims = {citation.claim_id for citation in self.citations}
        missing = sorted(material_claims - cited_claims)
        if missing:
            raise ValueError(
                "material claims require citations: " + ",".join(missing)
            )
        return self


class TerminalError(ArtifactBase):
    code: str
    message: str
    next_action: str | None = None


class RiskArtifact(ArtifactBase):
    risk_tier: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    likely_failure_modes: list[str]
    required_proof: list[str]
    reviewer_expertise: list[str]
    unavailable_signals: list[str] = Field(default_factory=list)


class CIDiagnosisArtifact(ArtifactBase):
    failure_class: Literal[
        "repository", "external", "flaky", "permission", "secret", "infrastructure"
    ]
    diagnosis: str
    reproduction_recipe: str | None = None
    validation_recipe: str | None = None
    patch_proposed: bool = False


class RefusalArtifact(ArtifactBase):
    failure_class: str
    missing_precondition: str
    next_action: str


class RecipeEvidence(BaseModel):
    recipe_name: str
    image_digest: str
    exit_code: int
    started_at: datetime
    finished_at: datetime
    output_hash: str = Field(min_length=64, max_length=64)


class PatchArtifact(ArtifactBase):
    base_sha: str
    unified_diff: str = Field(min_length=1, max_length=100_000)
    changed_paths: list[str]
    patch_hash: str = Field(min_length=64, max_length=64)
    reproduction: RecipeEvidence
    validation: RecipeEvidence
    policy_result: str

    @field_validator("base_sha")
    @classmethod
    def immutable_base_sha(cls, value: str) -> str:
        return _immutable_sha(value)

    @model_validator(mode="after")
    def patch_identity(self) -> PatchArtifact:
        import hashlib

        if self.base_sha != self.pinned_sha:
            raise ValueError("patch base SHA must match pinned SHA")
        if hashlib.sha256(self.unified_diff.encode()).hexdigest() != self.patch_hash:
            raise ValueError("patch hash does not match unified diff")
        if not self.changed_paths:
            raise ValueError("patch must declare changed paths")
        return self


class HumanReviewCreate(BaseModel):
    reviewer: str = Field(min_length=1, max_length=255)
    outcome: Literal["successful", "failed", "correctly_refused"]
    minutes: int = Field(ge=0, le=1_440)
    disposition: Literal["accepted", "edited", "rejected"]
    missing_evidence: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=10_000)


def _immutable_sha(value: str) -> str:
    if len(value) not in {40, 64} or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError("SHA must be lowercase hexadecimal and immutable")
    return value
