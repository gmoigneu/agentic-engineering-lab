from __future__ import annotations

import io
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import jwt

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


class GitHubAppArchiveReader:
    """Trusted GitHub App adapter that returns only a credential-free pinned snapshot."""

    def __init__(
        self,
        app_id: int,
        private_key: str,
        api_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
        max_archive_bytes: int = 100_000_000,
        max_file_bytes: int = 2_000_000,
    ) -> None:
        self._app_id = app_id
        self._private_key = private_key
        self._client = client or httpx.Client(base_url=api_url, follow_redirects=True, timeout=120)
        self._max_archive_bytes = max_archive_bytes
        self._max_file_bytes = max_file_bytes

    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot:
        if len(pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in pinned_sha
        ):
            raise ValueError("GitHub archive requires an immutable SHA")
        token = self._installation_token(repository_id)
        repository = self._client.get(
            f"/repositories/{repository_id}", headers=self._headers(token)
        )
        repository.raise_for_status()
        full_name = repository.json().get("full_name")
        if not isinstance(full_name, str) or full_name.count("/") != 1:
            raise ValueError("GitHub repository response is missing its canonical name")
        with self._client.stream(
            "GET",
            f"/repos/{full_name}/tarball/{pinned_sha}",
            headers=self._headers(token),
        ) as response:
            response.raise_for_status()
            archive = bytearray()
            for chunk in response.iter_bytes():
                archive.extend(chunk)
                if len(archive) > self._max_archive_bytes:
                    raise ValueError("repository archive exceeds the configured size limit")
        return RepositorySnapshot(pinned_sha, self._read_archive(bytes(archive)))

    def _installation_token(self, repository_id: int) -> str:
        now = datetime.now(UTC)
        app_jwt = jwt.encode(
            {
                "iat": int((now - timedelta(seconds=30)).timestamp()),
                "exp": int((now + timedelta(minutes=9)).timestamp()),
                "iss": str(self._app_id),
            },
            self._private_key,
            algorithm="RS256",
        )
        installation = self._client.get(
            f"/repositories/{repository_id}/installation", headers=self._headers(app_jwt)
        )
        installation.raise_for_status()
        installation_id = installation.json().get("id")
        if not isinstance(installation_id, int):
            raise ValueError("GitHub installation response is missing its ID")
        token_response = self._client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers=self._headers(app_jwt),
            json={
                "repository_ids": [repository_id],
                "permissions": {"contents": "read", "metadata": "read"},
            },
        )
        token_response.raise_for_status()
        token = token_response.json().get("token")
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub token response is invalid")
        return token

    def _read_archive(self, content: bytes) -> dict[str, str]:
        files: dict[str, str] = {}
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as archive:
            members = archive.getmembers()
            roots = {member.name.split("/", 1)[0] for member in members if member.name}
            if len(roots) != 1:
                raise ValueError("GitHub archive has an invalid root")
            root = next(iter(roots))
            for member in members:
                if member.issym() or member.islnk():
                    continue
                if not member.isfile() or member.size > self._max_file_bytes:
                    continue
                prefix = f"{root}/"
                if not member.name.startswith(prefix):
                    raise ValueError("GitHub archive path escaped its root")
                path = member.name[len(prefix) :]
                if not path or path.startswith("/") or ".." in path.split("/"):
                    raise ValueError("GitHub archive contains an unsafe path")
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                raw = extracted.read(self._max_file_bytes + 1)
                if b"\x00" in raw:
                    continue
                files[path] = raw.decode("utf-8", errors="replace")
        return files

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
