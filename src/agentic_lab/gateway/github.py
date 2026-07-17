from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import quote

import httpx

from agentic_lab.domain.enums import PolicyOutcome
from agentic_lab.gateway.github_app import GitHubAppInstallationAuth
from agentic_lab.gateway.patch_apply import apply_text_diff, parse_text_diff
from agentic_lab.policy.patch import PatchPolicy, PolicyResult
from agentic_lab.policy.push_gate import PushContext, evaluate_push_gate


class GitHubBranchWriter(Protocol):
    """Narrow port implemented only by the trusted GitHub App adapter."""

    def head_sha(self, repository_id: int, branch: str) -> str: ...

    def apply_unified_diff(
        self, repository_id: int, branch: str, base_sha: str, diff: str, run_id: str
    ) -> str: ...


class GitHubAppBranchWriter:
    """Narrow GitHub App writer using an atomic non-force Git ref update."""

    def __init__(
        self,
        app_id: int,
        private_key: str,
        allowed_repository_ids: frozenset[int],
        api_url: str = "https://api.github.com",
        client: httpx.Client | None = None,
    ) -> None:
        self._allowed_repository_ids = allowed_repository_ids
        self._client = client or httpx.Client(base_url=api_url, timeout=120)
        self._auth = GitHubAppInstallationAuth(app_id, private_key, self._client)

    def head_sha(self, repository_id: int, branch: str) -> str:
        self._authorize(repository_id, branch)
        token = self._auth.installation_token(
            repository_id, {"contents": "read", "metadata": "read"}
        )
        full_name = self._repository_name(repository_id, token)
        response = self._client.get(
            f"/repos/{full_name}/git/ref/heads/{quote(branch, safe='')}",
            headers=self._auth.headers(token),
        )
        response.raise_for_status()
        sha = response.json().get("object", {}).get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise ValueError("GitHub branch response is missing its immutable SHA")
        return sha

    def apply_unified_diff(
        self, repository_id: int, branch: str, base_sha: str, diff: str, run_id: str
    ) -> str:
        self._authorize(repository_id, branch)
        if (
            not run_id
            or len(base_sha) != 40
            or any(character not in "0123456789abcdef" for character in base_sha)
        ):
            raise ValueError("GitHub write requires run identity and an immutable base SHA")
        token = self._auth.installation_token(
            repository_id, {"contents": "write", "metadata": "read"}
        )
        headers = self._auth.headers(token)
        full_name = self._repository_name(repository_id, token)
        ref_path = f"/repos/{full_name}/git/ref/heads/{quote(branch, safe='')}"
        head_response = self._client.get(ref_path, headers=headers)
        head_response.raise_for_status()
        current_head = head_response.json().get("object", {}).get("sha")
        if current_head != base_sha:
            raise PermissionError("stale_head_sha")

        patches = parse_text_diff(diff)
        originals: dict[str, bytes] = {}
        for patch in patches:
            if patch.old_path is not None and patch.old_path not in originals:
                originals[patch.old_path] = self._file_content(
                    full_name, patch.old_path, base_sha, headers
                )
        applied = apply_text_diff(diff, originals)
        commit_response = self._client.get(
            f"/repos/{full_name}/git/commits/{base_sha}", headers=headers
        )
        commit_response.raise_for_status()
        base_tree = commit_response.json().get("tree", {}).get("sha")
        if not isinstance(base_tree, str):
            raise ValueError("GitHub commit response is missing its tree SHA")

        entries: list[dict[str, object]] = []
        for item in applied:
            if item.old_path is not None and item.old_path != item.new_path:
                entries.append(
                    {"path": item.old_path, "mode": "100644", "type": "blob", "sha": None}
                )
            if item.new_path is None:
                if item.old_path is not None and item.old_path == item.new_path:
                    entries.append(
                        {"path": item.old_path, "mode": "100644", "type": "blob", "sha": None}
                    )
                elif item.old_path is not None and not any(
                    entry["path"] == item.old_path for entry in entries
                ):
                    entries.append(
                        {"path": item.old_path, "mode": "100644", "type": "blob", "sha": None}
                    )
                continue
            blob = self._client.post(
                f"/repos/{full_name}/git/blobs",
                headers=headers,
                json={
                    "content": base64.b64encode(item.content or b"").decode(),
                    "encoding": "base64",
                },
            )
            blob.raise_for_status()
            blob_sha = blob.json().get("sha")
            if not isinstance(blob_sha, str):
                raise ValueError("GitHub blob response is missing its SHA")
            entries.append(
                {"path": item.new_path, "mode": "100644", "type": "blob", "sha": blob_sha}
            )

        tree = self._client.post(
            f"/repos/{full_name}/git/trees",
            headers=headers,
            json={"base_tree": base_tree, "tree": entries},
        )
        tree.raise_for_status()
        tree_sha = tree.json().get("sha")
        if not isinstance(tree_sha, str):
            raise ValueError("GitHub tree response is missing its SHA")
        commit = self._client.post(
            f"/repos/{full_name}/git/commits",
            headers=headers,
            json={
                "message": f"Agentic Engineering Lab validated patch\n\nRun-ID: {run_id}",
                "tree": tree_sha,
                "parents": [base_sha],
            },
        )
        commit.raise_for_status()
        commit_sha = commit.json().get("sha")
        if not isinstance(commit_sha, str) or len(commit_sha) != 40:
            raise ValueError("GitHub commit response is missing its SHA")
        update = self._client.patch(
            f"/repos/{full_name}/git/refs/heads/{quote(branch, safe='')}",
            headers=headers,
            json={"sha": commit_sha, "force": False},
        )
        update.raise_for_status()
        return commit_sha

    def _file_content(
        self, full_name: str, path: str, base_sha: str, headers: dict[str, str]
    ) -> bytes:
        response = self._client.get(
            f"/repos/{full_name}/contents/{quote(path, safe='/')}",
            headers=headers,
            params={"ref": base_sha},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise ValueError("GitHub source path is not a regular file")
        content = payload.get("content")
        if not isinstance(content, str):
            raise ValueError("GitHub content response is missing file data")
        try:
            return base64.b64decode("".join(content.split()), validate=True)
        except ValueError as error:
            raise ValueError("GitHub content response is invalid base64") from error

    def _repository_name(self, repository_id: int, token: str) -> str:
        response = self._client.get(
            f"/repositories/{repository_id}", headers=self._auth.headers(token)
        )
        response.raise_for_status()
        full_name = response.json().get("full_name")
        if not isinstance(full_name, str) or full_name.count("/") != 1:
            raise ValueError("GitHub repository response is missing its canonical name")
        return full_name

    def _authorize(self, repository_id: int, branch: str) -> None:
        if repository_id not in self._allowed_repository_ids:
            raise PermissionError("repository_not_allowlisted")
        if (
            not branch
            or len(branch) > 255
            or branch.startswith(("/", "."))
            or branch.endswith(("/", ".", ".lock"))
            or ".." in branch
            or any(character in branch for character in " ~^:?*[\\\x00")
        ):
            raise ValueError("GitHub branch name is invalid")


@dataclass(frozen=True)
class ValidatedPatchRequest:
    repository_id: int
    branch: str
    context: PushContext


def apply_validated_patch(
    writer: GitHubBranchWriter,
    request: ValidatedPatchRequest,
    patch_policy: PatchPolicy,
    audit: Callable[[str, PolicyResult], None] | None = None,
) -> str:
    """Sole write path. It rechecks the head SHA after policy evaluation."""
    decision = evaluate_push_gate(request.context, patch_policy)
    if audit is not None:
        audit("ci_push_gate", decision)
    if decision.outcome is not PolicyOutcome.ALLOW:
        raise PermissionError(decision.reason_code)
    if writer.head_sha(request.repository_id, request.branch) != request.context.pinned_sha:
        stale = PolicyResult(
            PolicyOutcome.DENY, "stale_head_sha", decision.changed_paths, decision.input_hash
        )
        if audit is not None:
            audit("ci_exact_sha_recheck", stale)
        raise PermissionError("stale_head_sha")
    result = writer.apply_unified_diff(
        request.repository_id,
        request.branch,
        request.context.pinned_sha,
        request.context.diff,
        request.context.run_id,
    )
    if audit is not None:
        audit("ci_github_write", decision)
    return result
