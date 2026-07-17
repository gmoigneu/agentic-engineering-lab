from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from agentic_lab.domain.enums import AgentRole
from agentic_lab.evaluation.fixtures import EvaluationCase
from agentic_lab.executor.launcher import ContainerRunner, default_docker_runner, launch_recipe
from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest
from agentic_lab.tools.snapshot import RepositorySnapshot

REPOSITORY = "gmoigneu/agentic-engineering-lab-eval"
REMOTE_URLS = {
    f"https://github.com/{REPOSITORY}.git",
    f"git@github.com:{REPOSITORY}.git",
}
SELECTOR = "tests/test_scenarios.py::test_dev_01_pagination_boundary"
PATCH = """--- a/src/eval_service/pagination.py
+++ b/src/eval_service/pagination.py
@@ -1,3 +1,3 @@
 def page(items: list[int], number: int, size: int) -> list[int]:
-    start = number * size
+    start = (number - 1) * size
     return items[start : start + size]
"""

SnapshotLoader = Callable[[Path, str], RepositorySnapshot]


def _run(arguments: list[str], *, cwd: Path) -> bytes:
    return subprocess.run(
        arguments,
        cwd=cwd,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    ).stdout


def _snapshot_at(checkout: Path, sha: str) -> RepositorySnapshot:
    origin = _run(["git", "remote", "get-url", "origin"], cwd=checkout).decode().strip()
    if origin not in REMOTE_URLS:
        raise ValueError("checkout origin is not the approved evaluation repository")
    names = _run(["git", "ls-tree", "-r", "--name-only", "-z", sha], cwd=checkout)
    paths = [item.decode() for item in names.split(b"\0") if item]
    files: dict[str, str] = {}
    for path in paths:
        content = _run(["git", "show", f"{sha}:{path}"], cwd=checkout)
        if b"\0" in content:
            raise ValueError(f"evaluation snapshot contains a binary file at {path}")
        files[path] = content.decode("utf-8")
    return RepositorySnapshot(sha, files)


def _execute(
    manifest: ExecutionManifest,
    fixture: EvaluationCase,
    snapshot: RepositorySnapshot,
    runner: ContainerRunner,
) -> dict[str, object]:
    requests = (
        RecipeRequest(
            "executor-probe-reproduce",
            fixture.pinned_sha,
            "reproduce",
            {"selector": SELECTOR},
        ),
        RecipeRequest(
            "executor-probe-validate",
            fixture.pinned_sha,
            "validate_patch",
            {"selector": SELECTOR, "unified_diff": PATCH},
        ),
        RecipeRequest(
            "executor-probe-lint",
            fixture.pinned_sha,
            "lint",
            {},
        ),
    )
    results = [launch_recipe(runner, manifest, request, snapshot) for request in requests]
    exit_codes = [result["exit_code"] for result in results]
    if exit_codes != [1, 0, 0]:
        diagnostics = [
            {
                "recipe_name": result["recipe_name"],
                "exit_code": result["exit_code"],
                "stdout_excerpt": result["stdout_excerpt"],
                "stderr_excerpt": result["stderr_excerpt"],
            }
            for result in results
        ]
        raise RuntimeError(
            "executor probe returned unexpected results "
            + json.dumps(diagnostics, sort_keys=True)
        )
    return {
        "status": "passed",
        "source_sha": fixture.pinned_sha,
        "image": manifest.recipes["reproduce"].image,
        "reproduce_exit_code": exit_codes[0],
        "validate_patch_exit_code": exit_codes[1],
        "lint_exit_code": exit_codes[2],
        "output_hashes": [result["output_hash"] for result in results],
    }


def probe(
    manifest_path: Path,
    fixture_path: Path,
    checkout: Path,
    *,
    runner: ContainerRunner | None = None,
    snapshot_loader: SnapshotLoader = _snapshot_at,
) -> dict[str, object]:
    manifest = ExecutionManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    fixture = EvaluationCase.model_validate_json(fixture_path.read_text(encoding="utf-8"))
    if manifest.repository != REPOSITORY or manifest.repository_id != fixture.repository_id:
        raise ValueError("manifest and fixture repository identity do not match")
    if fixture.role is not AgentRole.CI or fixture.case_id != "ci-dev-01":
        raise ValueError("executor probe requires the approved ci-dev-01 fixture")
    snapshot = snapshot_loader(checkout.resolve(), fixture.pinned_sha)
    if runner is not None:
        return _execute(manifest, fixture, snapshot, runner)
    with TemporaryDirectory(prefix="agentic-lab-executor-probe-") as transport_root:
        return _execute(
            manifest,
            fixture,
            snapshot,
            default_docker_runner(Path(transport_root)),
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("checkout", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("evaluation/manifests/eval-v1.json"),
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=Path("evaluation/fixtures/ci/development/dev-01.json"),
    )
    arguments = parser.parse_args()
    result = probe(
        arguments.manifest.resolve(),
        arguments.fixture.resolve(),
        arguments.checkout.resolve(),
    )
    print(json.dumps({**result, "completed_at": datetime.now(UTC).isoformat()}))


if __name__ == "__main__":
    main()
