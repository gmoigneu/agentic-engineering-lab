from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_lab.db.models import Artifact, PullRequestOptIn, Run
from agentic_lab.domain.enums import AgentRole, PolicyOutcome, RunStatus
from agentic_lab.domain.schemas import PatchArtifact
from agentic_lab.gateway.github import (
    GitHubBranchWriter,
    ValidatedPatchRequest,
    apply_validated_patch,
)
from agentic_lab.policy.audit import record_decision
from agentic_lab.policy.patch import PatchPolicy, PolicyResult
from agentic_lab.policy.push_gate import PushContext, evaluate_push_gate
from agentic_lab.runs.artifacts import store_artifact
from agentic_lab.runs.service import transition_run


def push_validated_patch(
    session: Session,
    run: Run,
    artifact: PatchArtifact,
    branch: str,
    observed_head_sha: str,
    same_repository_branch: bool,
    reproduction_passed: bool,
    validation_passed: bool,
    failure_class: str,
    writer: GitHubBranchWriter,
    patch_policy: PatchPolicy,
    actor: str = "worker",
) -> str | None:
    """Execute the only durable CI write flow after all evidence exists."""
    if run.role is not AgentRole.CI or run.status is not RunStatus.EVALUATING:
        raise ValueError("only evaluating CI runs can enter the push gate")
    if artifact.run_id != run.id or artifact.pinned_sha != run.pinned_sha:
        raise ValueError("patch artifact identity does not match the durable run")
    if run.pull_number is None or not branch:
        transition_run(session, run, RunStatus.REFUSED, "missing_pull_request_branch", actor)
        return None

    opt_in = session.get(PullRequestOptIn, (run.repository_id, run.pull_number))
    prior_attempts = (
        session.scalar(
            select(func.count(Artifact.id)).where(
                Artifact.run_id == run.id, Artifact.kind == "patch"
            )
        )
        or 0
    )
    context = PushContext(
        run_id=str(run.id),
        pinned_sha=run.pinned_sha,
        observed_head_sha=observed_head_sha,
        patch_base_sha=artifact.base_sha,
        opt_in_expires_at=opt_in.expires_at if opt_in else None,
        same_repository_branch=same_repository_branch,
        reproduction_passed=reproduction_passed,
        validation_passed=validation_passed,
        failure_class=failure_class,
        attempt_count=prior_attempts,
        diff=artifact.unified_diff,
    )
    decision = evaluate_push_gate(context, patch_policy)
    if decision.outcome is PolicyOutcome.ALLOW and set(decision.changed_paths) != set(
        artifact.changed_paths
    ):
        decision = PolicyResult(
            PolicyOutcome.DENY,
            "changed_paths_mismatch",
            decision.changed_paths,
            decision.input_hash,
        )
    record_decision(session, run.id, "ci_push_precheck", decision)
    store_artifact(session, artifact, "patch")
    if decision.outcome is PolicyOutcome.DENY:
        terminal = (
            RunStatus.SUPERSEDED if decision.reason_code == "stale_head_sha" else RunStatus.REFUSED
        )
        transition_run(session, run, terminal, decision.reason_code, actor)
        return None

    transition_run(session, run, RunStatus.READY_TO_PUSH, "ci_push_precheck_passed", actor)
    transition_run(session, run, RunStatus.PUSHING, "ci_exact_sha_recheck_started", actor)

    def audit(policy_name: str, result: PolicyResult) -> None:
        record_decision(session, run.id, policy_name, result)

    try:
        commit_sha = apply_validated_patch(
            writer,
            ValidatedPatchRequest(run.repository_id, branch, context),
            patch_policy,
            audit,
        )
    except PermissionError as error:
        transition_run(session, run, RunStatus.REFUSED, str(error), actor)
        return None
    transition_run(
        session,
        run,
        RunStatus.SUCCEEDED,
        "validated_patch_pushed",
        actor,
        {"commit_sha": commit_sha, "pushed_at": datetime.now(UTC).isoformat()},
    )
    return commit_sha
