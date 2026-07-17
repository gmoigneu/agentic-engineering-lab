from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Protocol

from agentic_lab.domain.enums import AgentRole
from agentic_lab.tools.snapshot import RepositorySnapshot


class GitHubReadPort(Protocol):
    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot: ...


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

    def _audit(self, run_id: str, outcome: str, reason: str, input_hash: str) -> None:
        if self.audit_port is not None:
            self.audit_port.record(run_id, "github_snapshot_read", outcome, reason, input_hash)
