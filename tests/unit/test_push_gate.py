from datetime import UTC, datetime, timedelta

from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.policy.patch import PatchPolicy
from agentic_lab.policy.push_gate import PushContext, evaluate_push_gate


def _context(**updates: object) -> PushContext:
    values: dict[str, object] = {
        "run_id": "run-1",
        "pinned_sha": "a" * 40,
        "observed_head_sha": "a" * 40,
        "patch_base_sha": "a" * 40,
        "opt_in_expires_at": datetime.now(UTC) + timedelta(hours=1),
        "same_repository_branch": True,
        "reproduction_passed": True,
        "validation_passed": True,
        "failure_class": "repository",
        "attempt_count": 0,
        "diff": "--- a/backend/app/service.py\n+++ b/backend/app/service.py\n+fix",
    }
    values.update(updates)
    return PushContext(**values)  # type: ignore[arg-type]


def test_push_gate_allows_only_complete_safe_context() -> None:
    policy = PatchPolicy(("backend/**/*.py",), ())
    assert evaluate_push_gate(_context(), policy).outcome is PolicyOutcome.ALLOW


def test_push_gate_refuses_stale_or_secret_patch() -> None:
    policy = PatchPolicy(("backend/**/*.py",), ())
    assert (
        evaluate_push_gate(_context(observed_head_sha="b" * 40), policy).reason_code
        == "stale_head_sha"
    )
    assert (
        evaluate_push_gate(
            _context(diff="+++ b/backend/app/service.py\n+ghp_" + "a" * 36), policy
        ).reason_code
        == "secret_detection"
    )
