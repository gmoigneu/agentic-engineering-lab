from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from agentic_lab.tools.snapshot import RepositorySnapshot


class RecipeExecutionRequest(BaseModel):
    schema_version: Literal["recipe-request-v1"] = "recipe-request-v1"
    run_id: str = Field(min_length=1, max_length=255)
    source_sha: str = Field(min_length=40, max_length=64)
    manifest_version: str = Field(min_length=1, max_length=100)
    recipe_name: str = Field(min_length=1, max_length=100)
    adapter: Literal["noop_v1", "pytest_v1", "pytest_after_patch_v1", "ruff_check_v1"]
    arguments: dict[str, Any]
    image_digest: str = Field(min_length=72, max_length=500)
    timeout_seconds: int = Field(gt=0, le=3_600)
    expected_output_artifacts: list[str] = Field(default_factory=list)

    @field_validator("source_sha")
    @classmethod
    def immutable_sha(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("recipe request requires an immutable lowercase SHA")
        return value

    @field_validator("expected_output_artifacts")
    @classmethod
    def safe_artifact_paths(cls, value: list[str]) -> list[str]:
        for item in value:
            candidate = PurePosixPath(item)
            if not item or candidate.is_absolute() or ".." in candidate.parts or "\x00" in item:
                raise ValueError("recipe artifacts must be relative output paths")
        return value


class RecipeOutputArtifact(BaseModel):
    path: str
    size_bytes: int = Field(ge=0)
    content_hash: str = Field(min_length=64, max_length=64)


class RecipeExecutionResult(BaseModel):
    schema_version: Literal["recipe-result-v1"] = "recipe-result-v1"
    run_id: str
    source_sha: str
    manifest_version: str
    recipe_name: str
    adapter: str
    image_digest: str
    started_at: datetime
    finished_at: datetime
    exit_code: int
    stdout_hash: str = Field(min_length=64, max_length=64)
    stderr_hash: str = Field(min_length=64, max_length=64)
    stdout_excerpt: str = Field(max_length=8_000)
    stderr_excerpt: str = Field(max_length=8_000)
    redacted: bool = False
    artifacts: list[RecipeOutputArtifact] = Field(default_factory=list)

    def verify_identity(self, request: RecipeExecutionRequest) -> None:
        expected = (
            request.run_id,
            request.source_sha,
            request.manifest_version,
            request.recipe_name,
            request.adapter,
            request.image_digest,
        )
        actual = (
            self.run_id,
            self.source_sha,
            self.manifest_version,
            self.recipe_name,
            self.adapter,
            self.image_digest,
        )
        if actual != expected:
            raise ValueError("executor result identity does not match its request")
        if self.finished_at < self.started_at:
            raise ValueError("executor result timestamps are invalid")


@dataclass(frozen=True)
class PreparedTransport:
    run_root: Path
    host_run_root: Path
    source_directory: Path
    input_directory: Path
    workspace_directory: Path
    output_directory: Path
    request_path: Path
    result_path: Path

    def host_path(self, directory: Path) -> Path:
        return self.host_run_root / directory.relative_to(self.run_root)


class ExecutorTransport:
    def __init__(self, root: Path, host_root: Path | None = None) -> None:
        self.root = root.resolve()
        self.host_root = (host_root or root).resolve()

    def prepare(
        self, snapshot: RepositorySnapshot, request: RecipeExecutionRequest
    ) -> PreparedTransport:
        if snapshot.pinned_sha != request.source_sha:
            raise ValueError("executor snapshot does not match the recipe request SHA")
        run_key = hashlib.sha256(f"{request.run_id}:{request.recipe_name}".encode()).hexdigest()[
            :24
        ]
        run_root = self.root / run_key
        host_run_root = self.host_root / run_key
        run_root.mkdir(parents=True, exist_ok=False, mode=0o700)
        source = run_root / "source"
        input_directory = run_root / "input"
        workspace = run_root / "workspace"
        output = run_root / "output"
        for directory in (source, input_directory, workspace, output):
            directory.mkdir(mode=0o700)
        for relative, content in snapshot.files.items():
            destination = self._safe_destination(source, relative)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination.write_text(content, encoding="utf-8")
            destination.chmod(0o400)
        for directory in sorted(source.rglob("*"), reverse=True):
            if directory.is_dir():
                directory.chmod(0o500)
        source.chmod(0o500)
        request_path = input_directory / "request.json"
        request_path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")
        request_path.chmod(0o400)
        input_directory.chmod(0o500)
        return PreparedTransport(
            run_root=run_root,
            host_run_root=host_run_root,
            source_directory=source,
            input_directory=input_directory,
            workspace_directory=workspace,
            output_directory=output,
            request_path=request_path,
            result_path=output / "result.json",
        )

    @staticmethod
    def load_result(
        prepared: PreparedTransport, request: RecipeExecutionRequest
    ) -> RecipeExecutionResult:
        if not prepared.result_path.is_file() or prepared.result_path.is_symlink():
            raise ValueError("executor did not produce its typed result")
        if prepared.result_path.stat().st_size > 1_000_000:
            raise ValueError("executor result exceeds the size limit")
        result = RecipeExecutionResult.model_validate_json(prepared.result_path.read_text())
        result.verify_identity(request)
        declared = {artifact.path for artifact in result.artifacts}
        expected = set(request.expected_output_artifacts)
        if not expected.issubset(declared):
            raise ValueError("executor result is missing an expected artifact")
        for artifact in result.artifacts:
            path = ExecutorTransport._safe_destination(prepared.output_directory, artifact.path)
            if not path.is_file() or path.is_symlink():
                raise ValueError("executor artifact path is invalid")
            content = path.read_bytes()
            if len(content) != artifact.size_bytes:
                raise ValueError("executor artifact size does not match its result")
            if hashlib.sha256(content).hexdigest() != artifact.content_hash:
                raise ValueError("executor artifact hash does not match its result")
        return result

    @staticmethod
    def _safe_destination(root: Path, relative: str) -> Path:
        candidate = PurePosixPath(relative)
        if candidate.is_absolute() or ".." in candidate.parts or "\x00" in relative:
            raise ValueError("executor transport path must be relative")
        destination = root.joinpath(*candidate.parts)
        resolved_parent = destination.parent.resolve()
        if root.resolve() not in {resolved_parent, *resolved_parent.parents}:
            raise ValueError("executor transport path escaped its root")
        return destination


def stable_result_hash(result: RecipeExecutionResult) -> str:
    payload = json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def restricted_executor_environment(workspace: Path | None = None) -> dict[str, str]:
    environment = {
        "HOME": "/tmp",
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "PYTHONNOUSERSITE": "1",
    }
    if workspace is not None:
        environment["PYTHONPATH"] = str(workspace / "src")
    return environment
