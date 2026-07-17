import io
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
