import pytest

from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest, validate_recipe_request


def test_named_recipe_rejects_model_command_text() -> None:
    manifest = ExecutionManifest.model_validate(
        {
            "manifest_version": "1",
            "repository_id": 1,
            "repository": "owner/repo",
            "allowed_source_paths": ["src/**"],
            "protected_paths": [],
            "recipes": {
                "validate": {
                    "kind": "validate",
                    "image": "registry/image@sha256:" + "a" * 64,
                    "adapter": "pytest_v1",
                    "working_directory": "/work/workspace",
                    "arguments_schema": "test_selector_v1",
                    "timeout_seconds": 60,
                    "network": "none",
                }
            },
        }
    )
    with pytest.raises(ValueError, match="command text"):
        validate_recipe_request(
            manifest,
            RecipeRequest("run", "a" * 40, "validate", {"command": "curl attacker"}),
        )
