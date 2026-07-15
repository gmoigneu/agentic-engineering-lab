from agentic_lab.executor.launcher import launch_recipe
from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest


class Runner:
    def run(self, spec, recipe_name, arguments):
        assert spec.network == "none"
        assert spec.environment == {}
        return 0


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
                    "working_directory": "/workspace",
                    "arguments_schema": "v1",
                    "timeout_seconds": 1,
                    "network": "none",
                }
            },
        }
    )
    result = launch_recipe(Runner(), manifest, RecipeRequest("run", "a" * 40, "check", {}))
    assert result["exit_code"] == 0
