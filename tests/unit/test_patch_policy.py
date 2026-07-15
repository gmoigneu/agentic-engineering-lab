from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.policy.patch import PatchPolicy, validate_unified_diff

POLICY = PatchPolicy(
    allowed_source_paths=("backend/**/*.py",),
    protected_paths=("backend/**/auth*.py",),
)


def test_allows_only_manifest_source_paths() -> None:
    result = validate_unified_diff(
        "--- a/backend/app/service.py\n+++ b/backend/app/service.py\n+fix", POLICY
    )
    assert result.outcome is PolicyOutcome.ALLOW
    assert result.changed_paths == ("backend/app/service.py",)


def test_refuses_test_and_protected_paths() -> None:
    test_result = validate_unified_diff("+++ b/backend/tests/test_service.py\n+change", POLICY)
    auth_result = validate_unified_diff("+++ b/backend/app/auth_service.py\n+change", POLICY)
    assert test_result.reason_code == "test_or_dependency_path"
    assert auth_result.reason_code == "manifest_protected_path"
