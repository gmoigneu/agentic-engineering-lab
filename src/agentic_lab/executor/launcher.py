from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import docker
from docker.types import Mount

from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest, validate_recipe_request
from agentic_lab.executor.transport import (
    ExecutorTransport,
    RecipeExecutionRequest,
    RecipeExecutionResult,
    stable_result_hash,
)
from agentic_lab.tools.snapshot import RepositorySnapshot


@dataclass(frozen=True)
class ExecutorSpec:
    run_id: str
    source_sha: str
    image: str
    network: str
    environment: dict[str, str]
    working_directory: str
    timeout_seconds: int
    container_user: str
    read_only_snapshot: bool = True
    writable_output_only: bool = True
    read_only_root_filesystem: bool = True
    no_new_privileges: bool = True
    dropped_capabilities: bool = True
    docker_socket: bool = False
    host_home: bool = False


class ContainerRunner(Protocol):
    def run(
        self,
        spec: ExecutorSpec,
        request: RecipeExecutionRequest,
        snapshot: RepositorySnapshot,
    ) -> RecipeExecutionResult: ...


class DockerContainerRunner:
    def __init__(
        self,
        transport: ExecutorTransport,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self.transport = transport
        self.client_factory = client_factory or docker.from_env

    def run(
        self,
        spec: ExecutorSpec,
        request: RecipeExecutionRequest,
        snapshot: RepositorySnapshot,
    ) -> RecipeExecutionResult:
        if spec.environment or spec.network != "none":
            raise ValueError("executor environment and network must remain empty")
        if (
            not all(
                (
                    spec.read_only_snapshot,
                    spec.writable_output_only,
                    spec.read_only_root_filesystem,
                    spec.no_new_privileges,
                    spec.dropped_capabilities,
                )
            )
            or spec.docker_socket
            or spec.host_home
        ):
            raise ValueError("executor security boundary is incomplete")
        prepared = self.transport.prepare(snapshot, request)
        mounts = {
            "/work/source": prepared.host_path(prepared.source_directory),
            "/work/input": prepared.host_path(prepared.input_directory),
            "/work/workspace": prepared.host_path(prepared.workspace_directory),
            "/work/output": prepared.host_path(prepared.output_directory),
        }
        child_mounts = [
            Mount("/work/source", str(mounts["/work/source"]), type="bind", read_only=True),
            Mount("/work/input", str(mounts["/work/input"]), type="bind", read_only=True),
            Mount("/work/workspace", str(mounts["/work/workspace"]), type="bind"),
            Mount("/work/output", str(mounts["/work/output"]), type="bind"),
        ]
        adapter_arguments = [
            "--request",
            "/work/input/request.json",
            "--source",
            "/work/source",
            "--workspace",
            "/work/workspace",
            "--output",
            "/work/output",
            "--result",
            "/work/output/result.json",
        ]
        client = self.client_factory()
        container = None
        try:
            container = client.containers.run(
                spec.image,
                adapter_arguments,
                entrypoint="agentic-lab-recipe-adapter",
                detach=True,
                remove=False,
                network_mode="none",
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=256,
                mem_limit="1g",
                nano_cpus=1_000_000_000,
                user=spec.container_user,
                working_dir="/work/workspace",
                tmpfs={"/tmp": "rw,noexec,nosuid,nodev,size=64m"},
                mounts=child_mounts,
                environment={},
            )
            status = container.wait(timeout=spec.timeout_seconds + 30)
            exit_code = status.get("StatusCode")
            if exit_code != 0:
                raise RuntimeError(f"disposable executor failed with status {exit_code}")
        finally:
            if container is not None:
                container.remove(force=True)
            client.close()
        return self.transport.load_result(prepared, request)


def launch_recipe(
    runner: ContainerRunner,
    manifest: ExecutionManifest,
    request: RecipeRequest,
    snapshot: RepositorySnapshot,
) -> dict[str, object]:
    recipe = validate_recipe_request(manifest, request)
    spec = ExecutorSpec(
        request.run_id,
        request.source_sha,
        recipe.image,
        recipe.network,
        {},
        recipe.working_directory,
        recipe.timeout_seconds,
        f"{os.getuid()}:{os.getgid()}",
    )
    execution_request = RecipeExecutionRequest(
        run_id=request.run_id,
        source_sha=request.source_sha,
        manifest_version=manifest.manifest_version,
        recipe_name=request.recipe_name,
        adapter=recipe.adapter,
        arguments=request.arguments,
        image_digest=recipe.image,
        timeout_seconds=recipe.timeout_seconds,
        expected_output_artifacts=recipe.expected_output_artifacts,
    )
    result = runner.run(spec, execution_request, snapshot)
    result.verify_identity(execution_request)
    payload = result.model_dump(mode="json")
    payload["output_hash"] = stable_result_hash(result)
    return payload


def default_docker_runner(root: Path, host_root: Path | None = None) -> DockerContainerRunner:
    return DockerContainerRunner(ExecutorTransport(root, host_root))
