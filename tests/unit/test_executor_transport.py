from __future__ import annotations

import stat
from datetime import UTC, datetime
from pathlib import Path

from agentic_lab.executor.adapter import execute_request
from agentic_lab.executor.launcher import DockerContainerRunner, ExecutorSpec
from agentic_lab.executor.transport import (
    ExecutorTransport,
    RecipeExecutionRequest,
    RecipeExecutionResult,
)
from agentic_lab.tools.snapshot import RepositorySnapshot


def _request() -> RecipeExecutionRequest:
    return RecipeExecutionRequest(
        run_id="run-1",
        source_sha="a" * 40,
        manifest_version="v1",
        recipe_name="validate",
        adapter="noop_v1",
        arguments={},
        image_digest="executor@sha256:" + "b" * 64,
        timeout_seconds=10,
    )


def _result(request: RecipeExecutionRequest) -> RecipeExecutionResult:
    now = datetime.now(UTC)
    return RecipeExecutionResult(
        run_id=request.run_id,
        source_sha=request.source_sha,
        manifest_version=request.manifest_version,
        recipe_name=request.recipe_name,
        adapter=request.adapter,
        image_digest=request.image_digest,
        started_at=now,
        finished_at=now,
        exit_code=0,
        stdout_hash="c" * 64,
        stderr_hash="d" * 64,
        stdout_excerpt="",
        stderr_excerpt="",
    )


def test_transport_materializes_read_only_source_and_typed_identity(tmp_path: Path) -> None:
    transport = ExecutorTransport(tmp_path)
    request = _request()
    prepared = transport.prepare(
        RepositorySnapshot(request.source_sha, {"src/app.py": "value = 1\n"}), request
    )

    assert stat.S_IMODE((prepared.source_directory / "src/app.py").stat().st_mode) == 0o400
    assert stat.S_IMODE(prepared.source_directory.stat().st_mode) == 0o500
    assert "secret" not in prepared.request_path.read_text()
    prepared.result_path.write_text(_result(request).model_dump_json())
    assert transport.load_result(prepared, request).exit_code == 0


def test_fixed_adapter_runs_without_shell_or_inherited_secrets(tmp_path: Path) -> None:
    request = _request()
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    source.mkdir()
    (source / "app.py").write_text("value = 1\n")

    result = execute_request(request, source, workspace, output)

    assert result.exit_code == 0
    assert result.adapter == "noop_v1"
    assert (workspace / "app.py").read_text() == "value = 1\n"


def test_patch_adapter_applies_diff_then_runs_fixed_pytest(tmp_path: Path) -> None:
    request = RecipeExecutionRequest(
        run_id="run-patch",
        source_sha="a" * 40,
        manifest_version="v1",
        recipe_name="validate_patch",
        adapter="pytest_after_patch_v1",
        arguments={
            "selector": "test_app.py",
            "unified_diff": (
                '--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = "old"\n+value = "new"\n'
            ),
        },
        image_digest="executor@sha256:" + "b" * 64,
        timeout_seconds=10,
    )
    source = tmp_path / "source"
    workspace = tmp_path / "workspace"
    output = tmp_path / "output"
    source.mkdir()
    (source / "app.py").write_text('value = "old"\n')
    (source / "test_app.py").write_text(
        'from app import value\n\n\ndef test_value():\n    assert value == "new"\n'
    )

    result = execute_request(request, source, workspace, output)

    assert result.exit_code == 0
    assert (workspace / "app.py").read_text() == 'value = "new"\n'


def test_docker_runner_builds_a_credential_free_hardened_invocation(
    tmp_path: Path,
) -> None:
    request = _request()
    transport = ExecutorTransport(tmp_path)
    captured: dict[str, object] = {}

    class Container:
        def wait(self, timeout):  # type: ignore[no-untyped-def]
            captured["timeout"] = timeout
            return {"StatusCode": 0}

        def remove(self, force):  # type: ignore[no-untyped-def]
            captured["removed"] = force

    class Containers:
        def run(self, image, arguments, **kwargs):  # type: ignore[no-untyped-def]
            captured.update({"image": image, "arguments": arguments, **kwargs})
            result_path = next(tmp_path.glob("*/output")) / "result.json"
            result_path.write_text(_result(request).model_dump_json())
            return Container()

    class Client:
        containers = Containers()

        def close(self):
            captured["closed"] = True

    runner = DockerContainerRunner(transport, client_factory=Client)
    spec = ExecutorSpec(
        run_id=request.run_id,
        source_sha=request.source_sha,
        image=request.image_digest,
        network="none",
        environment={},
        working_directory="/work/workspace",
        timeout_seconds=10,
        container_user="65532:65532",
    )

    result = runner.run(
        spec,
        request,
        RepositorySnapshot(request.source_sha, {"src/app.py": "value = 1\n"}),
    )

    assert result.exit_code == 0
    assert captured["network_mode"] == "none"
    assert captured["read_only"] is True
    assert captured["cap_drop"] == ["ALL"]
    assert captured["security_opt"] == ["no-new-privileges:true"]
    assert captured["entrypoint"] == "agentic-lab-recipe-adapter"
    assert captured["environment"] == {}
    assert captured["removed"] is True
    assert captured["closed"] is True
    assert "docker.sock" not in str(captured["mounts"])
