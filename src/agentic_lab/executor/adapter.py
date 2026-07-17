from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

from agentic_lab.executor.adapters import adapter_argv
from agentic_lab.executor.transport import (
    RecipeExecutionRequest,
    RecipeExecutionResult,
    RecipeOutputArtifact,
    restricted_executor_environment,
)
from agentic_lab.gateway.patch_apply import apply_text_diff
from agentic_lab.gateway.redaction import redact


def execute_request(
    request: RecipeExecutionRequest,
    source_directory: Path,
    workspace_directory: Path,
    output_directory: Path,
) -> RecipeExecutionResult:
    if workspace_directory.exists() and any(workspace_directory.iterdir()):
        raise ValueError("executor workspace must start empty")
    workspace_directory.mkdir(parents=True, exist_ok=True)
    workspace_directory.chmod(0o700)
    output_directory.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_directory, workspace_directory, dirs_exist_ok=True, symlinks=False)
    workspace_directory.chmod(0o700)
    for path in workspace_directory.rglob("*"):
        path.chmod(0o700 if path.is_dir() else 0o600)
    if request.adapter == "pytest_after_patch_v1":
        _apply_workspace_diff(workspace_directory, request.arguments["unified_diff"])
    argv = adapter_argv(request)
    started = datetime.now(UTC)
    try:
        completed = subprocess.run(
            argv,
            cwd=workspace_directory,
            env=restricted_executor_environment(workspace_directory),
            capture_output=True,
            timeout=request.timeout_seconds,
            check=False,
        )
        exit_code = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        stdout = error.stdout or b""
        stderr = b"recipe timed out"
    finished = datetime.now(UTC)
    stdout_result = redact(stdout[:8_000].decode("utf-8", errors="replace"))
    stderr_result = redact(stderr[:8_000].decode("utf-8", errors="replace"))
    detected = stdout_result.detected or stderr_result.detected
    artifacts: list[RecipeOutputArtifact] = []
    for relative in request.expected_output_artifacts:
        source = _safe_artifact_path(workspace_directory, relative)
        if not source.is_file() or source.is_symlink():
            continue
        content = source.read_bytes()
        if len(content) > 10_000_000:
            continue
        if b"\x00" not in content:
            artifact_redaction = redact(content.decode("utf-8", errors="replace"))
            if artifact_redaction.detected:
                detected = True
                continue
        destination = _safe_artifact_path(output_directory, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        artifacts.append(
            RecipeOutputArtifact(
                path=relative,
                size_bytes=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
            )
        )
    return RecipeExecutionResult(
        run_id=request.run_id,
        source_sha=request.source_sha,
        manifest_version=request.manifest_version,
        recipe_name=request.recipe_name,
        adapter=request.adapter,
        image_digest=request.image_digest,
        started_at=started,
        finished_at=finished,
        exit_code=exit_code,
        stdout_hash=hashlib.sha256(stdout).hexdigest(),
        stderr_hash=hashlib.sha256(stderr).hexdigest(),
        stdout_excerpt=(
            "output blocked by redaction policy" if stdout_result.detected else stdout_result.text
        ),
        stderr_excerpt=(
            "output blocked by redaction policy" if stderr_result.detected else stderr_result.text
        ),
        redacted=detected,
        artifacts=artifacts,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--result", required=True)
    arguments = parser.parse_args()
    request_path = Path(arguments.request)
    if request_path.stat().st_size > 1_000_000:
        raise ValueError("executor request exceeds the size limit")
    request = RecipeExecutionRequest.model_validate_json(request_path.read_text())
    result = execute_request(
        request,
        Path(arguments.source),
        Path(arguments.workspace),
        Path(arguments.output),
    )
    result_path = Path(arguments.result)
    result_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _safe_artifact_path(root: Path, relative: str) -> Path:
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or "\x00" in relative:
        raise ValueError("executor artifact path is unsafe")
    destination = root.joinpath(*candidate.parts)
    resolved_parent = destination.parent.resolve()
    if root.resolve() not in {resolved_parent, *resolved_parent.parents}:
        raise ValueError("executor artifact path escaped its root")
    return destination


def _apply_workspace_diff(workspace: Path, diff: object) -> None:
    if not isinstance(diff, str):
        raise ValueError("patch adapter requires a unified diff")
    originals: dict[str, bytes] = {}
    from agentic_lab.gateway.patch_apply import parse_text_diff

    for patch in parse_text_diff(diff):
        if patch.old_path is not None:
            source = _safe_artifact_path(workspace, patch.old_path)
            if not source.is_file() or source.is_symlink():
                raise ValueError("patch base file is unavailable in the workspace")
            originals[patch.old_path] = source.read_bytes()
    for item in apply_text_diff(diff, originals):
        if item.old_path is not None and item.old_path != item.new_path:
            old_path = _safe_artifact_path(workspace, item.old_path)
            old_path.unlink()
        if item.new_path is None:
            if item.old_path is not None:
                old_path = _safe_artifact_path(workspace, item.old_path)
                old_path.unlink(missing_ok=True)
            continue
        destination = _safe_artifact_path(workspace, item.new_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(item.content or b"")


if __name__ == "__main__":
    main()
