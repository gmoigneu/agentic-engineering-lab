from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.gateway.redaction import redact
from agentic_lab.policy.patch import PatchPolicy, PolicyResult, validate_unified_diff


@dataclass(frozen=True)
class PushContext:
    run_id: str
    pinned_sha: str
    observed_head_sha: str
    patch_base_sha: str
    opt_in_expires_at: datetime | None
    same_repository_branch: bool
    reproduction_passed: bool
    validation_passed: bool
    failure_class: str
    attempt_count: int
    diff: str


def evaluate_push_gate(
    context: PushContext, patch_policy: PatchPolicy, now: datetime | None = None
) -> PolicyResult:
    now = now or datetime.now(UTC)
    if context.opt_in_expires_at is None or _as_utc(context.opt_in_expires_at) <= now:
        return _deny(context, "missing_or_expired_opt_in")
    if not context.same_repository_branch:
        return _deny(context, "fork_branch_refused")
    if (
        context.observed_head_sha != context.pinned_sha
        or context.patch_base_sha != context.pinned_sha
    ):
        return _deny(context, "stale_head_sha")
    if context.failure_class != "repository" or not context.reproduction_passed:
        return _deny(context, "unreproduced_or_external_failure")
    if not context.validation_passed:
        return _deny(context, "validation_not_passed")
    if context.attempt_count != 0:
        return _deny(context, "one_attempt_policy")
    secret_result = redact(context.diff)
    if secret_result.detected:
        return _deny(context, "secret_detection")
    return validate_unified_diff(context.diff, patch_policy)


def _deny(context: PushContext, reason: str) -> PolicyResult:
    return PolicyResult(PolicyOutcome.DENY, reason, (), redact(context.diff).content_hash)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value
