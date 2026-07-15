from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

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


class RunTransitionSummary(BaseModel):
    from_status: RunStatus | None
    to_status: RunStatus
    reason_code: str
    actor: str
    occurred_at: datetime


class RunDetail(RunSummary):
    transitions: list[RunTransitionSummary]


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


class HumanReviewCreate(BaseModel):
    reviewer: str = Field(min_length=1, max_length=255)
    outcome: str = Field(min_length=1, max_length=100)
    minutes: int = Field(ge=0, le=1_440)
    disposition: Literal["accepted", "edited", "rejected"]
    missing_evidence: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=10_000)
