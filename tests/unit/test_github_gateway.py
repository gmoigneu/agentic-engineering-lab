from datetime import UTC, datetime, timedelta

import pytest

from agentic_lab.gateway.github import ValidatedPatchRequest, apply_validated_patch
from agentic_lab.policy.patch import PatchPolicy
from agentic_lab.policy.push_gate import PushContext


class Writer:
    def __init__(self, head: str) -> None:
        self.head = head
        self.applied = False

    def head_sha(self, repository_id: int, branch: str) -> str:
        return self.head

    def apply_unified_diff(self, repository_id: int, branch: str, base_sha: str, diff: str) -> str:
        self.applied = True
        return "b" * 40


def _request(head: str = "a" * 40) -> ValidatedPatchRequest:
    context = PushContext(
        "run",
        "a" * 40,
        head,
        "a" * 40,
        datetime.now(UTC) + timedelta(hours=1),
        True,
        True,
        True,
        "repository",
        0,
        "--- a/backend/app/service.py\n+++ b/backend/app/service.py\n+fix",
    )
    return ValidatedPatchRequest(1, "feature", context)


def test_gateway_rechecks_head_before_only_write_operation() -> None:
    writer = Writer("b" * 40)
    with pytest.raises(PermissionError, match="stale_head_sha"):
        apply_validated_patch(writer, _request(), PatchPolicy(("backend/**/*.py",), ()))
    assert not writer.applied
