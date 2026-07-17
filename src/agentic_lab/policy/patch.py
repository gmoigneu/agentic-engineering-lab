from __future__ import annotations

import fnmatch
import hashlib
import re
from dataclasses import dataclass

from agentic_lab.domain.enums import PolicyOutcome

_FORBIDDEN_PATH_PARTS = (
    ".github/",
    "migrations/",
    "alembic/",
    "infra/",
    "infrastructure/",
    "auth/",
    "authentication/",
    "authorization/",
    "secrets/",
)
_FORBIDDEN_NAMES = frozenset(
    {
        "dockerfile",
        "compose.yaml",
        "compose.yml",
        "pyproject.toml",
        "package.json",
        "cargo.toml",
        "go.mod",
        "requirements.txt",
        "poetry.lock",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)
_FORBIDDEN_SUFFIXES = (".lock", ".pem", ".key")
_TEST_MARKERS = ("/tests/", "/test_", "_test.py", ".test.", ".spec.")
_DIFF_HEADER = re.compile(r"^(---|\+\+\+) (?:[ab]/)?([^\t\n]+)", re.MULTILINE)


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
    if (
        "GIT binary patch" in diff
        or re.search(r"^Binary files .+ differ$", diff, re.MULTILINE)
        or "new file mode 120000" in diff
        or "Subproject commit" in diff
    ):
        return PolicyResult(PolicyOutcome.DENY, "binary_or_link_change", (), input_hash)
    paths = _changed_paths(diff)
    if not paths:
        return PolicyResult(PolicyOutcome.DENY, "no_changed_source_path", (), input_hash)
    if len(paths) > policy.max_changed_files:
        return PolicyResult(PolicyOutcome.DENY, "too_many_changed_files", paths, input_hash)
    for path in paths:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        if path.startswith("../") or path.startswith("/") or "\x00" in path:
            return PolicyResult(PolicyOutcome.DENY, "unsafe_path", paths, input_hash)
        if any(marker in lowered for marker in _FORBIDDEN_PATH_PARTS) or any(
            part.startswith("auth") for part in lowered.split("/")[:-1]
        ):
            return PolicyResult(PolicyOutcome.DENY, "protected_path", paths, input_hash)
        if (
            name in _FORBIDDEN_NAMES
            or lowered.endswith(_FORBIDDEN_SUFFIXES)
            or lowered.startswith("test_")
            or lowered.startswith("tests/")
            or any(marker in lowered for marker in _TEST_MARKERS)
        ):
            return PolicyResult(PolicyOutcome.DENY, "test_or_dependency_path", paths, input_hash)
        if any(fnmatch.fnmatch(path, pattern) for pattern in policy.protected_paths):
            return PolicyResult(PolicyOutcome.DENY, "manifest_protected_path", paths, input_hash)
        if (
            name.startswith(("auth", "authorization", "authentication"))
            or "_auth" in name
            or name.endswith(".tf")
        ):
            return PolicyResult(PolicyOutcome.DENY, "protected_path", paths, input_hash)
        if not any(fnmatch.fnmatch(path, pattern) for pattern in policy.allowed_source_paths):
            return PolicyResult(PolicyOutcome.DENY, "path_not_allowlisted", paths, input_hash)
    return PolicyResult(PolicyOutcome.ALLOW, "source_only_patch", paths, input_hash)


def _changed_paths(diff: str) -> tuple[str, ...]:
    paths: set[str] = set()
    for _, raw_path in _DIFF_HEADER.findall(diff):
        path = raw_path.strip()
        if path != "/dev/null":
            paths.add(path)
    return tuple(sorted(paths))
