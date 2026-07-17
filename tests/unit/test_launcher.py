from datetime import UTC, datetime

from agentic_lab.executor.launcher import launch_recipe
from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest
from agentic_lab.executor.transport import RecipeExecutionResult
from agentic_lab.tools.snapshot import RepositorySnapshot


class Runner:
    def run(self, spec, request, snapshot):
        assert spec.network == "none"
        assert spec.environment == {}
        assert spec.read_only_root_filesystem
        assert request.adapter == "noop_v1"
        assert snapshot.pinned_sha == request.source_sha
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
            stdout_hash="b" * 64,
            stderr_hash="c" * 64,
            stdout_excerpt="",
            stderr_excerpt="",
        )


def test_launcher_has_no_executor_secrets():
    manifest = ExecutionManifest.model_validate(
        {
            "manifest_version": "1",
            "repository_id": 1,
            "repository": "a/b",
            "allowed_source_paths": ["src/**"],
            "protected_paths": [],
            "recipes": {
                "check": {
                    "kind": "validate",
                    "image": "x@sha256:" + "a" * 64,
                    "adapter": "noop_v1",
                    "working_directory": "/work/workspace",
                    "arguments_schema": "none_v1",
                    "timeout_seconds": 1,
                    "network": "none",
                }
            },
        }
    )
    result = launch_recipe(
        Runner(),
        manifest,
        RecipeRequest("run", "a" * 40, "check", {}),
        RepositorySnapshot("a" * 40, {"src/app.py": "value = 1\n"}),
    )
    assert result["exit_code"] == 0
    assert len(result["output_hash"]) == 64
