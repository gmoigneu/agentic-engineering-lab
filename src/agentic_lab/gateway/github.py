from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.policy.patch import PatchPolicy, PolicyResult
from agentic_lab.policy.push_gate import PushContext, evaluate_push_gate


class GitHubBranchWriter(Protocol):
    """Narrow port implemented only by the trusted GitHub App adapter."""

    def head_sha(self, repository_id: int, branch: str) -> str: ...

    def apply_unified_diff(
        self, repository_id: int, branch: str, base_sha: str, diff: str
    ) -> str: ...


@dataclass(frozen=True)
class ValidatedPatchRequest:
    repository_id: int
    branch: str
    context: PushContext


def apply_validated_patch(
    writer: GitHubBranchWriter,
    request: ValidatedPatchRequest,
    patch_policy: PatchPolicy,
    audit: Callable[[str, PolicyResult], None] | None = None,
) -> str:
    """Sole write path. It rechecks the head SHA after policy evaluation."""
    decision = evaluate_push_gate(request.context, patch_policy)
    if audit is not None:
        audit("ci_push_gate", decision)
    if decision.outcome is not PolicyOutcome.ALLOW:
        raise PermissionError(decision.reason_code)
    if writer.head_sha(request.repository_id, request.branch) != request.context.pinned_sha:
        stale = PolicyResult(
            PolicyOutcome.DENY, "stale_head_sha", decision.changed_paths, decision.input_hash
        )
        if audit is not None:
            audit("ci_exact_sha_recheck", stale)
        raise PermissionError("stale_head_sha")
    result = writer.apply_unified_diff(
        request.repository_id,
        request.branch,
        request.context.pinned_sha,
        request.context.diff,
    )
    if audit is not None:
        audit("ci_github_write", decision)
    return result
