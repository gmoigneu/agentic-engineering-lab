from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass

from agentic_lab.domain.enums import PolicyOutcome

_FORBIDDEN_PATH_PARTS = (".github/", "migrations/", "infra/", "auth/", "authorization/", "secrets/")
_FORBIDDEN_SUFFIXES = (".lock", "package-lock.json", "poetry.lock", "requirements.txt")
_TEST_MARKERS = ("/tests/", "/test_", "_test.py", ".test.", ".spec.")
_DIFF_PATH = re.compile(r"^\+\+\+ b/(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class PatchPolicy:
    allowed_source_paths: tuple[str, ...]
    protected_paths: tuple[str, ...]
    max_changed_files: int = 20
    max_patch_bytes: int = 100_000


@dataclass(frozen=True)
class PolicyResult:
    outcome: PolicyOutcome
    reason_code: str
    changed_paths: tuple[str, ...]
    input_hash: str


def validate_unified_diff(diff: str, policy: PatchPolicy) -> PolicyResult:
    input_hash = hashlib.sha256(diff.encode()).hexdigest()
    if len(diff.encode()) > policy.max_patch_bytes:
        return PolicyResult(PolicyOutcome.DENY, "patch_too_large", (), input_hash)
    if "GIT binary patch" in diff or "new file mode 120000" in diff or "Subproject commit" in diff:
        return PolicyResult(PolicyOutcome.DENY, "binary_or_link_change", (), input_hash)
    paths = tuple(sorted(set(_DIFF_PATH.findall(diff))))
    if not paths:
        return PolicyResult(PolicyOutcome.DENY, "no_changed_source_path", (), input_hash)
    if len(paths) > policy.max_changed_files:
        return PolicyResult(PolicyOutcome.DENY, "too_many_changed_files", paths, input_hash)
    for path in paths:
        if path == "/dev/null" or path.startswith("../") or path.startswith("/"):
            return PolicyResult(PolicyOutcome.DENY, "unsafe_path", paths, input_hash)
        if any(marker in path for marker in _FORBIDDEN_PATH_PARTS):
            return PolicyResult(PolicyOutcome.DENY, "protected_path", paths, input_hash)
        if path.endswith(_FORBIDDEN_SUFFIXES) or any(marker in path for marker in _TEST_MARKERS):
            return PolicyResult(PolicyOutcome.DENY, "test_or_dependency_path", paths, input_hash)
        if any(fnmatch.fnmatch(path, pattern) for pattern in policy.protected_paths):
            return PolicyResult(PolicyOutcome.DENY, "manifest_protected_path", paths, input_hash)
        if not any(fnmatch.fnmatch(path, pattern) for pattern in policy.allowed_source_paths):
            return PolicyResult(PolicyOutcome.DENY, "path_not_allowlisted", paths, input_hash)
    return PolicyResult(PolicyOutcome.ALLOW, "source_only_patch", paths, input_hash)
