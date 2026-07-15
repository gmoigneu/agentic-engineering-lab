from __future__ import annotations

from dataclasses import dataclass

from agentic_lab.tools.snapshot import RepositorySnapshot


@dataclass(frozen=True)
class Archive:
    repository_id: int
    sha: str
    files: dict[str, str]


class PinnedArchiveReader:
    """Small adapter seam for the GitHub App archive client."""

    def __init__(self, archives: dict[tuple[int, str], Archive]) -> None:
        self._archives = archives

    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot:
        archive = self._archives.get((repository_id, pinned_sha))
        if archive is None or archive.sha != pinned_sha:
            raise FileNotFoundError("pinned archive unavailable")
        return RepositorySnapshot(pinned_sha, dict(archive.files))
