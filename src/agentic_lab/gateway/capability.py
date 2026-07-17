from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from agentic_lab.domain.enums import AgentRole
from agentic_lab.gateway.github_evidence import CheckEvidence, PullRequestDiffEvidence
from agentic_lab.tools.snapshot import RepositorySnapshot


class GitHubReadPort(Protocol):
    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot: ...

    def fetch_pull_request_diff(
        self, repository_id: int, pull_number: int, pinned_sha: str
    ) -> PullRequestDiffEvidence: ...

    def fetch_check_evidence(
        self, repository_id: int, check_run_id: int, pinned_sha: str
    ) -> CheckEvidence: ...


class CapabilityAuditPort(Protocol):
    def record(
        self, run_id: str, policy_name: str, outcome: str, reason_code: str, input_hash: str
    ) -> None: ...


@dataclass(frozen=True)
class CapabilityGateway:
    """Role-gated facade. It deliberately has no generic REST method or write method."""

    read_port: GitHubReadPort
    allowed_repository_ids: frozenset[int]
    audit_port: CapabilityAuditPort | None = None

    def fetch_snapshot(
        self, run_id: str, role: AgentRole, repository_id: int, pinned_sha: str
    ) -> RepositorySnapshot:
        role_value = role.value if isinstance(role, AgentRole) else str(role)
        input_hash = hashlib.sha256(
            f"{role_value}:{repository_id}:{pinned_sha}".encode()
        ).hexdigest()
        if role not in {AgentRole.SCOUT, AgentRole.ASSESSOR, AgentRole.CI}:
            self._audit(run_id, "deny", "role_cannot_read", input_hash)
            raise PermissionError("role cannot read a repository snapshot")
        if repository_id not in self.allowed_repository_ids:
            self._audit(run_id, "deny", "repository_not_allowlisted", input_hash)
            raise PermissionError("repository is not allowlisted")
        if len(pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in pinned_sha
        ):
            self._audit(run_id, "deny", "mutable_source_reference", input_hash)
            raise PermissionError("mutable source reference refused")
        self._audit(run_id, "allow", "pinned_snapshot_read", input_hash)
        return self.read_port.fetch_snapshot(repository_id, pinned_sha)

    def fetch_pull_request_diff(
        self,
        run_id: str,
        role: AgentRole,
        repository_id: int,
        pull_number: int,
        pinned_sha: str,
    ) -> PullRequestDiffEvidence:
        input_hash = self._input_hash(role, repository_id, pinned_sha, str(pull_number))
        if role not in {AgentRole.ASSESSOR, AgentRole.CI}:
            self._audit_named(
                run_id, "github_pull_request_diff_read", "deny", "role_cannot_read_diff", input_hash
            )
            raise PermissionError("role cannot read pull-request diff evidence")
        self._authorize_repository_and_sha(
            run_id, "github_pull_request_diff_read", repository_id, pinned_sha, input_hash
        )
        if pull_number < 1:
            self._audit_named(
                run_id, "github_pull_request_diff_read", "deny", "invalid_pull_number", input_hash
            )
            raise PermissionError("invalid pull number")
        self._audit_named(
            run_id, "github_pull_request_diff_read", "allow", "pinned_diff_read", input_hash
        )
        return self.read_port.fetch_pull_request_diff(repository_id, pull_number, pinned_sha)

    def fetch_check_evidence(
        self,
        run_id: str,
        role: AgentRole,
        repository_id: int,
        check_run_id: int,
        pinned_sha: str,
    ) -> CheckEvidence:
        input_hash = self._input_hash(role, repository_id, pinned_sha, str(check_run_id))
        if role is not AgentRole.CI:
            self._audit_named(
                run_id, "github_check_evidence_read", "deny", "role_cannot_read_check", input_hash
            )
            raise PermissionError("role cannot read check evidence")
        self._authorize_repository_and_sha(
            run_id, "github_check_evidence_read", repository_id, pinned_sha, input_hash
        )
        if check_run_id < 1:
            self._audit_named(
                run_id, "github_check_evidence_read", "deny", "invalid_check_run_id", input_hash
            )
            raise PermissionError("invalid check-run ID")
        self._audit_named(
            run_id, "github_check_evidence_read", "allow", "pinned_check_read", input_hash
        )
        return self.read_port.fetch_check_evidence(repository_id, check_run_id, pinned_sha)

    def _authorize_repository_and_sha(
        self,
        run_id: str,
        policy_name: str,
        repository_id: int,
        pinned_sha: str,
        input_hash: str,
    ) -> None:
        if repository_id not in self.allowed_repository_ids:
            self._audit_named(run_id, policy_name, "deny", "repository_not_allowlisted", input_hash)
            raise PermissionError("repository is not allowlisted")
        if len(pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in pinned_sha
        ):
            self._audit_named(run_id, policy_name, "deny", "mutable_source_reference", input_hash)
            raise PermissionError("mutable source reference refused")

    @staticmethod
    def _input_hash(role: AgentRole, repository_id: int, pinned_sha: str, resource_id: str) -> str:
        role_value = role.value if isinstance(role, AgentRole) else str(role)
        return hashlib.sha256(
            f"{role_value}:{repository_id}:{pinned_sha}:{resource_id}".encode()
        ).hexdigest()

    def _audit(self, run_id: str, outcome: str, reason: str, input_hash: str) -> None:
        self._audit_named(run_id, "github_snapshot_read", outcome, reason, input_hash)

    def _audit_named(
        self, run_id: str, policy_name: str, outcome: str, reason: str, input_hash: str
    ) -> None:
        if self.audit_port is not None:
            self.audit_port.record(run_id, policy_name, outcome, reason, input_hash)
