from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest, validate_recipe_request


@dataclass(frozen=True)
class ExecutorSpec:
    run_id: str
    source_sha: str
    image: str
    network: str
    environment: dict[str, str]


class ContainerRunner(Protocol):
    def run(self, spec: ExecutorSpec, recipe_name: str, arguments: dict[str, object]) -> int: ...


def launch_recipe(
    runner: ContainerRunner, manifest: ExecutionManifest, request: RecipeRequest
) -> dict[str, object]:
    recipe = validate_recipe_request(manifest, request)
    spec = ExecutorSpec(request.run_id, request.source_sha, recipe.image, recipe.network, {})
    started = datetime.now(UTC)
    exit_code = runner.run(spec, request.recipe_name, request.arguments)
    return {
        "run_id": request.run_id,
        "source_sha": request.source_sha,
        "recipe": request.recipe_name,
        "image": recipe.image,
        "exit_code": exit_code,
        "started_at": started.isoformat(),
        "finished_at": datetime.now(UTC).isoformat(),
    }
