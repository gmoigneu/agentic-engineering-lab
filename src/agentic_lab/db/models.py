from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from agentic_lab.db.base import Base
from agentic_lab.domain.enums import AgentRole, PolicyOutcome, RunSource, RunStatus

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("delivery_id", name="uq_webhook_events_delivery_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_name: Mapped[str | None] = mapped_column(String(100))
    repository_id: Mapped[int | None] = mapped_column(Integer, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(String(100))


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        Index("ix_runs_repository_sha", "repository_id", "pinned_sha"),
        Index("ix_runs_pull_sha", "pull_number", "pinned_sha"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    role: Mapped[AgentRole] = mapped_column(Enum(AgentRole, native_enum=False), nullable=False)
    source: Mapped[RunSource] = mapped_column(Enum(RunSource, native_enum=False), nullable=False)
    repository_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    pull_number: Mapped[int | None] = mapped_column(Integer)
    check_run_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    pinned_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    task_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, native_enum=False), nullable=False, index=True
    )
    manifest_version: Mapped[str] = mapped_column(String(100), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64))
    model_config: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    budget: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, default=dict, nullable=False)
    evaluation_case_id: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunTransition(Base):
    __tablename__ = "run_transitions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[RunStatus | None] = mapped_column(Enum(RunStatus, native_enum=False))
    to_status: Mapped[RunStatus] = mapped_column(Enum(RunStatus, native_enum=False), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSON_TYPE, default=dict, nullable=False
    )


class RunLease(Base):
    __tablename__ = "run_leases"

    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True
    )
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("run_id", "kind", name="uq_artifacts_run_kind"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(100))
    schema_version: Mapped[str] = mapped_column(String(32))
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    redaction_state: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CitationRecord(Base):
    __tablename__ = "citations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), index=True
    )
    claim_id: Mapped[str] = mapped_column(String(100))
    source_kind: Mapped[str] = mapped_column(String(100))
    locator: Mapped[str] = mapped_column(String(2_000))
    pinned_sha: Mapped[str] = mapped_column(String(64))
    excerpt_hash: Mapped[str] = mapped_column(String(64))


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    policy_name: Mapped[str] = mapped_column(String(100))
    input_hash: Mapped[str] = mapped_column(String(64))
    outcome: Mapped[PolicyOutcome] = mapped_column(Enum(PolicyOutcome, native_enum=False))
    reason_code: Mapped[str] = mapped_column(String(100))
    metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON_TYPE, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_tool_calls_sequence"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    tool_name: Mapped[str] = mapped_column(String(100))
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    status: Mapped[str] = mapped_column(String(32))
    duration_ms: Mapped[int] = mapped_column(Integer)
    policy_decision_id: Mapped[UUID | None] = mapped_column(ForeignKey("policy_decisions.id"))


class ModelCall(Base):
    __tablename__ = "model_calls"
    __table_args__ = (UniqueConstraint("run_id", "sequence", name="uq_model_calls_sequence"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    model_id: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(255))
    settings: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    usage: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    billed_cost: Mapped[float] = mapped_column(nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer)
    langfuse_trace_id: Mapped[str | None] = mapped_column(String(255), index=True)


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    reviewer: Mapped[str] = mapped_column(String(255))
    outcome: Mapped[str] = mapped_column(String(100))
    minutes: Mapped[int] = mapped_column(Integer)
    disposition: Mapped[str] = mapped_column(String(100))
    missing_evidence: Mapped[list[str]] = mapped_column(JSON_TYPE, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TargetManifest(Base):
    __tablename__ = "target_manifests"
    __table_args__ = (
        UniqueConstraint("repository_id", "version", name="uq_manifest_repository_version"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[int] = mapped_column(Integer, index=True)
    version: Mapped[str] = mapped_column(String(100))
    content: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64))
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PullRequestOptIn(Base):
    __tablename__ = "pull_request_opt_ins"

    repository_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pull_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    enabled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    enabled_by: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    reason: Mapped[str] = mapped_column(Text)


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dataset_split: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluator_version: Mapped[str] = mapped_column(String(100), nullable=False)
    score_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunCausalLink(Base):
    __tablename__ = "run_causal_links"
    __table_args__ = (
        UniqueConstraint("source_run_id", "target_run_id", "relation", name="uq_run_causal_link"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RedactionEvent(Base):
    __tablename__ = "redaction_events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    detector_name: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locator: Mapped[str] = mapped_column(String(255), nullable=False)
    resolution_state: Mapped[str] = mapped_column(String(32), nullable=False, default="blocked")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class WebhookRunLink(Base):
    __tablename__ = "webhook_run_links"

    webhook_event_id: Mapped[UUID] = mapped_column(
        ForeignKey("webhook_events.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[UUID] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True, index=True
    )
