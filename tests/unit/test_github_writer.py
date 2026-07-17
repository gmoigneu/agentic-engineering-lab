from __future__ import annotations

import base64
import json

import httpx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_lab.gateway.github import GitHubAppBranchWriter


def test_github_app_writer_creates_git_objects_and_non_force_updates_the_branch() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    base_sha = "a" * 40
    commit_sha = "d" * 40
    token_permissions: list[dict[str, str]] = []
    writes: list[tuple[str, dict[str, object]]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/installation"):
            return httpx.Response(200, json={"id": 2})
        if path.endswith("/access_tokens"):
            token_permissions.append(json.loads(request.content)["permissions"])
            return httpx.Response(201, json={"token": "installation-secret"})
        if path == "/repositories/1":
            return httpx.Response(200, json={"full_name": "owner/repo"})
        if path == "/repos/owner/repo/git/ref/heads/feature":
            return httpx.Response(200, json={"object": {"sha": base_sha}})
        if path == "/repos/owner/repo/contents/src/app.py":
            return httpx.Response(
                200,
                json={
                    "type": "file",
                    "encoding": "base64",
                    "content": base64.b64encode(b"old\n").decode(),
                },
            )
        if path == f"/repos/owner/repo/git/commits/{base_sha}" and request.method == "GET":
            return httpx.Response(200, json={"tree": {"sha": "1" * 40}})
        if request.method in {"POST", "PATCH"}:
            payload = json.loads(request.content)
            writes.append((path, payload))
            if path.endswith("/git/blobs"):
                return httpx.Response(201, json={"sha": "2" * 40})
            if path.endswith("/git/trees"):
                return httpx.Response(201, json={"sha": "3" * 40})
            if path.endswith("/git/commits"):
                return httpx.Response(201, json={"sha": commit_sha})
            if path.endswith("/git/refs/heads/feature"):
                return httpx.Response(200, json={"object": {"sha": commit_sha}})
        raise AssertionError(f"unexpected GitHub request {request.method} {path}")

    writer = GitHubAppBranchWriter(
        1,
        pem,
        frozenset({1}),
        client=httpx.Client(
            base_url="https://api.github.test",
            transport=httpx.MockTransport(respond),
        ),
    )
    diff = "--- a/src/app.py\n+++ b/src/app.py\n@@ -1 +1 @@\n-old\n+new\n"

    assert writer.head_sha(1, "feature") == base_sha
    assert writer.apply_unified_diff(1, "feature", base_sha, diff, "run-123") == commit_sha

    assert token_permissions == [
        {"contents": "read", "metadata": "read"},
        {"contents": "write", "metadata": "read"},
    ]
    commit_payload = next(payload for path, payload in writes if path.endswith("/git/commits"))
    update_payload = next(
        payload for path, payload in writes if path.endswith("/git/refs/heads/feature")
    )
    assert "Run-ID: run-123" in commit_payload["message"]
    assert update_payload == {"sha": commit_sha, "force": False}
