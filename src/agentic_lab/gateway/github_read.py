from __future__ import annotations

import hashlib
import io
import re
import tarfile
from dataclasses import dataclass

import httpx

from agentic_lab.gateway.github_app import GitHubAppInstallationAuth
from agentic_lab.gateway.github_evidence import (
    CheckAnnotationEvidence,
    CheckEvidence,
    DiffFileEvidence,
    PullRequestDiffEvidence,
    bounded_untrusted_text,
    parse_diff_hunks,
)
from agentic_lab.tools.snapshot import RepositorySnapshot


@dataclass(frozen=True)
class Archive:
    repository_id: int
    sha: str
    files: dict[str, str]


class PinnedArchiveReader:
    """Small adapter seam for the GitHub App archive client."""

    def __init__(
        self,
        archives: dict[tuple[int, str], Archive],
        diffs: dict[tuple[int, int, str], PullRequestDiffEvidence] | None = None,
        checks: dict[tuple[int, int, str], CheckEvidence] | None = None,
    ) -> None:
        self._archives = archives
        self._diffs = diffs or {}
        self._checks = checks or {}

    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot:
        archive = self._archives.get((repository_id, pinned_sha))
        if archive is None or archive.sha != pinned_sha:
            raise FileNotFoundError("pinned archive unavailable")
        return RepositorySnapshot(pinned_sha, dict(archive.files))

    def fetch_pull_request_diff(
        self, repository_id: int, pull_number: int, pinned_sha: str
    ) -> PullRequestDiffEvidence:
        evidence = self._diffs.get((repository_id, pull_number, pinned_sha))
        if evidence is None or evidence.head_sha != pinned_sha:
            raise FileNotFoundError("pinned pull-request diff unavailable")
        return evidence.model_copy(deep=True)

    def fetch_check_evidence(
        self, repository_id: int, check_run_id: int, pinned_sha: str
    ) -> CheckEvidence:
        evidence = self._checks.get((repository_id, check_run_id, pinned_sha))
        if evidence is None or evidence.head_sha != pinned_sha:
            raise FileNotFoundError("pinned check evidence unavailable")
        return evidence.model_copy(deep=True)


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
        self._auth = GitHubAppInstallationAuth(app_id, private_key, self._client)
        self._max_archive_bytes = max_archive_bytes
        self._max_file_bytes = max_file_bytes

    def fetch_snapshot(self, repository_id: int, pinned_sha: str) -> RepositorySnapshot:
        if len(pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in pinned_sha
        ):
            raise ValueError("GitHub archive requires an immutable SHA")
        token = self._installation_token(repository_id, {"contents": "read", "metadata": "read"})
        full_name = self._repository_name(repository_id, token)
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

    def fetch_pull_request_diff(
        self, repository_id: int, pull_number: int, pinned_sha: str
    ) -> PullRequestDiffEvidence:
        self._validate_sha(pinned_sha)
        if pull_number < 1:
            raise ValueError("pull number must be positive")
        token = self._installation_token(
            repository_id,
            {"contents": "read", "metadata": "read", "pull_requests": "read"},
        )
        full_name = self._repository_name(repository_id, token)
        pull = self._client.get(
            f"/repos/{full_name}/pulls/{pull_number}", headers=self._headers(token)
        )
        pull.raise_for_status()
        payload = pull.json()
        head = payload.get("head") if isinstance(payload, dict) else None
        base = payload.get("base") if isinstance(payload, dict) else None
        if not isinstance(head, dict) or head.get("sha") != pinned_sha:
            raise ValueError("pull-request head does not match the pinned SHA")
        if not isinstance(base, dict) or not isinstance(base.get("sha"), str):
            raise ValueError("pull-request response is missing its base SHA")
        head_repository = head.get("repo")
        same_repository = (
            isinstance(head_repository, dict) and head_repository.get("id") == repository_id
        )
        head_ref = head.get("ref")
        if not isinstance(head_ref, str) or not head_ref:
            raise ValueError("pull-request response is missing its head branch")
        raw_files, truncated = self._paginated(
            f"/repos/{full_name}/pulls/{pull_number}/files",
            token,
            maximum=300,
        )
        files: list[DiffFileEvidence] = []
        allowed_statuses = {"added", "modified", "removed", "renamed", "copied", "changed"}
        for item in raw_files:
            path = item.get("filename")
            status = item.get("status")
            if not isinstance(path, str) or status not in allowed_statuses:
                raise ValueError("pull-request file response is invalid")
            patch = item.get("patch")
            patch_text = patch if isinstance(patch, str) else ""
            changes = int(item.get("changes") or 0)
            files.append(
                DiffFileEvidence(
                    path=path,
                    previous_path=(
                        item.get("previous_filename")
                        if isinstance(item.get("previous_filename"), str)
                        else None
                    ),
                    status=status,
                    additions=int(item.get("additions") or 0),
                    deletions=int(item.get("deletions") or 0),
                    changes=changes,
                    binary="unknown" if patch is None and changes else "no",
                    patch_hash=hashlib.sha256(patch_text.encode()).hexdigest(),
                    hunks=parse_diff_hunks(
                        patch_text,
                        pull_number=pull_number,
                        path=path,
                    ),
                )
            )
        return PullRequestDiffEvidence(
            repository_id=repository_id,
            pull_number=pull_number,
            base_sha=base["sha"],
            head_sha=pinned_sha,
            head_ref=head_ref,
            same_repository=same_repository,
            files=files,
            truncated=truncated,
        )

    def fetch_check_evidence(
        self, repository_id: int, check_run_id: int, pinned_sha: str
    ) -> CheckEvidence:
        self._validate_sha(pinned_sha)
        if check_run_id < 1:
            raise ValueError("check-run ID must be positive")
        token = self._installation_token(
            repository_id,
            {"checks": "read", "metadata": "read"},
        )
        full_name = self._repository_name(repository_id, token)
        response = self._client.get(
            f"/repos/{full_name}/check-runs/{check_run_id}", headers=self._headers(token)
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("head_sha") != pinned_sha:
            raise ValueError("check-run head does not match the pinned SHA")
        output_payload = payload.get("output")
        output: list = []
        if isinstance(output_payload, dict):
            for field in ("title", "summary", "text"):
                value = output_payload.get(field)
                if isinstance(value, str) and value:
                    output.append(
                        bounded_untrusted_text(
                            value,
                            f"check_run#{check_run_id}:output:{field}",
                        )
                    )
        raw_annotations, annotations_truncated = self._paginated(
            f"/repos/{full_name}/check-runs/{check_run_id}/annotations",
            token,
            maximum=300,
        )
        annotations: list[CheckAnnotationEvidence] = []
        for index, item in enumerate(raw_annotations, start=1):
            path = item.get("path")
            message = item.get("message")
            level = item.get("annotation_level")
            if (
                not isinstance(path, str)
                or not isinstance(message, str)
                or level not in {"notice", "warning", "failure"}
            ):
                raise ValueError("check annotation response is invalid")
            locator = f"check_run#{check_run_id}:annotation-{index}"
            annotations.append(
                CheckAnnotationEvidence(
                    locator=locator,
                    path=path,
                    start_line=int(item.get("start_line") or 1),
                    end_line=int(item.get("end_line") or item.get("start_line") or 1),
                    annotation_level=level,
                    title=item.get("title") if isinstance(item.get("title"), str) else None,
                    message=bounded_untrusted_text(message, locator),
                )
            )
        app = payload.get("app")
        log_excerpts, log_unknowns = self._github_actions_logs(
            repository_id,
            full_name,
            check_run_id,
            payload.get("details_url"),
        )
        return CheckEvidence(
            repository_id=repository_id,
            check_run_id=check_run_id,
            name=str(payload.get("name") or "unnamed check"),
            head_sha=pinned_sha,
            status=payload.get("status"),
            conclusion=(
                payload.get("conclusion") if isinstance(payload.get("conclusion"), str) else None
            ),
            app_slug=app.get("slug") if isinstance(app, dict) else None,
            started_at=(
                payload.get("started_at") if isinstance(payload.get("started_at"), str) else None
            ),
            completed_at=(
                payload.get("completed_at")
                if isinstance(payload.get("completed_at"), str)
                else None
            ),
            output=output,
            log_excerpts=log_excerpts,
            annotations=annotations,
            annotations_truncated=annotations_truncated,
            logs_available=bool(log_excerpts),
            unavailable_signals=log_unknowns,
        )

    def _github_actions_logs(
        self,
        repository_id: int,
        full_name: str,
        check_run_id: int,
        details_url: object,
    ) -> tuple[list, list[str]]:
        if not isinstance(details_url, str):
            return [], ["check_log_locator_unavailable"]
        match = re.fullmatch(
            rf"https://github\.com/{re.escape(full_name)}/actions/runs/\d+/job/(\d+)",
            details_url,
        )
        if match is None:
            return [], ["check_log_locator_unavailable"]
        try:
            token = self._installation_token(
                repository_id,
                {"actions": "read", "checks": "read", "metadata": "read"},
            )
            with self._client.stream(
                "GET",
                f"/repos/{full_name}/actions/jobs/{match.group(1)}/logs",
                headers=self._headers(token),
            ) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_bytes():
                    content.extend(chunk)
                    if len(content) > 2_000_000:
                        break
        except httpx.HTTPStatusError:
            return [], ["check_logs_permission_or_source_unavailable"]
        locator = f"check_run#{check_run_id}:github-actions-log"
        return [
            bounded_untrusted_text(
                bytes(content).decode("utf-8", errors="replace"),
                locator,
            )
        ], []

    def _installation_token(self, repository_id: int, permissions: dict[str, str]) -> str:
        return self._auth.installation_token(repository_id, permissions)

    def _repository_name(self, repository_id: int, token: str) -> str:
        repository = self._client.get(
            f"/repositories/{repository_id}", headers=self._headers(token)
        )
        repository.raise_for_status()
        full_name = repository.json().get("full_name")
        if not isinstance(full_name, str) or full_name.count("/") != 1:
            raise ValueError("GitHub repository response is missing its canonical name")
        return full_name

    def _paginated(
        self, path: str, token: str, *, maximum: int
    ) -> tuple[list[dict[str, object]], bool]:
        items: list[dict[str, object]] = []
        page = 1
        per_page = 100
        while len(items) < maximum:
            response = self._client.get(
                path,
                headers=self._headers(token),
                params={"per_page": per_page, "page": page},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                raise ValueError("GitHub paginated response is invalid")
            remaining = maximum - len(items)
            items.extend(payload[:remaining])
            if len(payload) < per_page:
                return items, False
            if len(payload) > remaining:
                return items, True
            page += 1
        probe = self._client.get(
            path,
            headers=self._headers(token),
            params={"per_page": 1, "page": page},
        )
        probe.raise_for_status()
        probe_payload = probe.json()
        return items, isinstance(probe_payload, list) and bool(probe_payload)

    @staticmethod
    def _validate_sha(pinned_sha: str) -> None:
        if len(pinned_sha) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in pinned_sha
        ):
            raise ValueError("GitHub evidence requires an immutable SHA")

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
        return GitHubAppInstallationAuth.headers(token)
