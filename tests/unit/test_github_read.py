import io
import json
import tarfile

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from agentic_lab.gateway.github_read import Archive, GitHubAppArchiveReader, PinnedArchiveReader


def test_reader_refuses_mutable_or_missing_archive():
    reader = PinnedArchiveReader({(1, "a" * 40): Archive(1, "a" * 40, {"src/a.py": "x"})})
    assert reader.fetch_snapshot(1, "a" * 40).read_file("src/a.py").text == "x"
    with pytest.raises(FileNotFoundError):
        reader.fetch_snapshot(1, "main")


def test_github_app_reader_returns_credential_free_snapshot() -> None:
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w:gz") as archive:
        content = b"value = 1\n"
        info = tarfile.TarInfo("owner-repo-sha/src/app.py")
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/installation"):
            assert request.headers["authorization"].startswith("Bearer ey")
            return httpx.Response(200, json={"id": 2})
        if request.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "installation-secret"})
        assert request.headers["authorization"] == "Bearer installation-secret"
        if request.url.path == "/repositories/1":
            return httpx.Response(200, json={"full_name": "owner/repo"})
        return httpx.Response(200, content=archive_buffer.getvalue())

    reader = GitHubAppArchiveReader(
        1,
        pem,
        client=httpx.Client(
            base_url="https://api.github.test",
            transport=httpx.MockTransport(respond),
        ),
    )
    snapshot = reader.fetch_snapshot(1, "a" * 40)
    assert snapshot.read_file("src/app.py").text == "value = 1"
    assert "installation-secret" not in repr(snapshot)


def test_github_app_reader_returns_sha_bound_redacted_diff_and_check_evidence() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    requested_permissions: list[dict[str, str]] = []
    secret = "ghp_" + "z" * 36

    def respond(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/installation"):
            return httpx.Response(200, json={"id": 2})
        if path.endswith("/access_tokens"):
            requested_permissions.append(json.loads(request.content)["permissions"])
            return httpx.Response(201, json={"token": "installation-secret"})
        if path == "/repositories/1":
            return httpx.Response(200, json={"full_name": "owner/repo"})
        if path == "/repos/owner/repo/pulls/7":
            return httpx.Response(
                200,
                json={
                    "base": {"sha": "b" * 40},
                    "head": {"sha": "a" * 40, "ref": "feature", "repo": {"id": 1}},
                },
            )
        if path == "/repos/owner/repo/pulls/7/files":
            return httpx.Response(
                200,
                json=[
                    {
                        "filename": "src/app.py",
                        "status": "modified",
                        "additions": 1,
                        "deletions": 1,
                        "changes": 2,
                        "patch": f"@@ -1 +1 @@\n-old\n+{secret}",
                    }
                ],
            )
        if path == "/repos/owner/repo/check-runs/9/annotations":
            return httpx.Response(
                200,
                json=[
                    {
                        "path": "src/app.py",
                        "start_line": 1,
                        "end_line": 1,
                        "annotation_level": "failure",
                        "message": f"failure included {secret}",
                    }
                ],
            )
        if path == "/repos/owner/repo/check-runs/9":
            return httpx.Response(
                200,
                json={
                    "name": "tests",
                    "head_sha": "a" * 40,
                    "status": "completed",
                    "conclusion": "failure",
                    "app": {"slug": "github-actions"},
                    "details_url": "https://github.com/owner/repo/actions/runs/8/job/10",
                    "output": {"title": "failed", "summary": "one test failed", "text": ""},
                },
            )
        if path == "/repos/owner/repo/actions/jobs/10/logs":
            return httpx.Response(200, text="pytest reported one failure")
        raise AssertionError(f"unexpected GitHub request {path}")

    reader = GitHubAppArchiveReader(
        1,
        pem,
        client=httpx.Client(
            base_url="https://api.github.test",
            transport=httpx.MockTransport(respond),
        ),
    )

    diff = reader.fetch_pull_request_diff(1, 7, "a" * 40)
    check = reader.fetch_check_evidence(1, 9, "a" * 40)

    assert diff.head_ref == "feature"
    assert diff.files[0].hunks[0].body.redacted
    assert check.annotations[0].message.redacted
    assert check.logs_available
    assert check.log_excerpts[0].text == "pytest reported one failure"
    assert secret not in diff.model_dump_json()
    assert secret not in check.model_dump_json()
    assert requested_permissions == [
        {"contents": "read", "metadata": "read", "pull_requests": "read"},
        {"checks": "read", "metadata": "read"},
        {"actions": "read", "checks": "read", "metadata": "read"},
    ]
