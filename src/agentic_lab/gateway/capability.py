from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentic_lab.domain.enums import AgentRole
from agentic_lab.tools.snapshot import RepositorySnapshot


class GitHubReadPort(Protocol):
    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot: ...


@dataclass(frozen=True)
class CapabilityGateway:
    """Role-gated facade. It deliberately has no generic REST method or write method."""

    read_port: GitHubReadPort
    allowed_repository_ids: frozenset[int]

    def fetch_snapshot(self, run_id: str, role: AgentRole, repository_id: int, pinned_sha: str) -> RepositorySnapshot:
        if role not in {AgentRole.SCOUT, AgentRole.ASSESSOR, AgentRole.CI}:
            raise PermissionError("role cannot read a repository snapshot")
        if repository_id not in self.allowed_repository_ids:
            raise PermissionError("repository is not allowlisted")
        if len(pinned_sha) not in {40, 64}:
            raise PermissionError("mutable source reference refused")
        return self.read_port.fetch_snapshot(repository_id, pinned_sha)
