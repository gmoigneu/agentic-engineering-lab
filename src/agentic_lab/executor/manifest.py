from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

ADAPTER_ARGUMENT_SCHEMAS = {
    "noop_v1": "none_v1",
    "pytest_v1": "test_selector_v1",
    "pytest_after_patch_v1": "patch_test_selector_v1",
    "ruff_check_v1": "none_v1",
}


class Recipe(BaseModel):
    kind: Literal["setup", "reproduce", "validate"]
    image: str
    adapter: Literal["noop_v1", "pytest_v1", "pytest_after_patch_v1", "ruff_check_v1"]
    working_directory: str
    arguments_schema: str
    timeout_seconds: int = Field(gt=0, le=3600)
    network: str
    required_local_services: list[str] = Field(default_factory=list)
    expected_output_artifacts: list[str] = Field(default_factory=list)

    @field_validator("image")
    @classmethod
    def immutable_image(cls, value: str) -> str:
        if not re.fullmatch(r"[^\s@]+@sha256:[0-9a-f]{64}", value):
            raise ValueError("recipe image must use an immutable digest")
        return value

    @field_validator("working_directory")
    @classmethod
    def confined_working_directory(cls, value: str) -> str:
        if value != "/work/workspace":
            raise ValueError("v1 recipes must run inside the ephemeral executor workspace")
        return value

    @field_validator("expected_output_artifacts")
    @classmethod
    def safe_output_artifacts(cls, value: list[str]) -> list[str]:
        if any(
            not item
            or item == "result.json"
            or item.startswith("/")
            or ".." in item.split("/")
            or "\x00" in item
            for item in value
        ):
            raise ValueError("output artifacts must be relative to the output directory")
        return value

    @field_validator("network")
    @classmethod
    def network_disabled(cls, value: str) -> str:
        if value != "none":
            raise ValueError("v1 recipes must disable network access")
        return value

    @model_validator(mode="after")
    def adapter_matches_arguments(self) -> Recipe:
        expected = ADAPTER_ARGUMENT_SCHEMAS[self.adapter]
        if self.arguments_schema != expected:
            raise ValueError(f"{self.adapter} requires the {expected} arguments schema")
        return self


class ManifestBudgets(BaseModel):
    max_model_turns: int = Field(default=12, ge=1, le=100)
    max_tool_calls: int = Field(default=40, ge=1, le=1_000)
    max_wall_seconds: int = Field(default=1_200, ge=1, le=86_400)
    max_usd: float = Field(default=3.0, gt=0, le=100)


class ExecutionManifest(BaseModel):
    manifest_version: str
    repository_id: int
    repository: str
    allowed_source_paths: list[str]
    protected_paths: list[str]
    recipes: dict[str, Recipe]
    redaction_patterns: list[str] = Field(default_factory=list)
    budgets: ManifestBudgets = Field(default_factory=ManifestBudgets)

    @field_validator("repository")
    @classmethod
    def canonical_repository(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
            raise ValueError("repository must be a canonical owner/name")
        return value

    @field_validator("allowed_source_paths", "protected_paths")
    @classmethod
    def safe_globs(cls, value: list[str]) -> list[str]:
        if any(not item or item.startswith("/") or ".." in item.split("/") for item in value):
            raise ValueError("manifest paths must be repository-relative globs")
        return value


@dataclass(frozen=True)
class RecipeRequest:
    run_id: str
    source_sha: str
    recipe_name: str
    arguments: dict[str, Any]


def validate_recipe_request(manifest: ExecutionManifest, request: RecipeRequest) -> Recipe:
    recipe = manifest.recipes.get(request.recipe_name)
    if recipe is None:
        raise ValueError("unknown manifest recipe")
    if not request.run_id or len(request.source_sha) not in {40, 64}:
        raise ValueError("run ID and immutable source SHA are required")
    if _contains_command_key(request.arguments):
        raise ValueError("recipe arguments cannot contain command text")
    _validate_arguments(recipe.arguments_schema, request.arguments)
    return recipe


def _contains_command_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            str(key).lower() in {"command", "cmd", "shell", "script"} or _contains_command_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_command_key(item) for item in value)
    return False


def _validate_arguments(schema: str, arguments: dict[str, Any]) -> None:
    if schema in {"v1", "none_v1"}:
        if arguments:
            raise ValueError(f"{schema} does not accept arguments")
        return
    if schema == "test_selector_v1":
        if set(arguments) - {"selector"} or not isinstance(arguments.get("selector"), str):
            raise ValueError("test_selector_v1 requires only a string selector")
        selector = arguments["selector"]
        if (
            not selector
            or len(selector) > 500
            or any(character in selector for character in ";|&`$\n")
        ):
            raise ValueError("test selector contains unsafe characters")
        return
    if schema == "patch_test_selector_v1":
        if set(arguments) != {"selector", "unified_diff"}:
            raise ValueError("patch_test_selector_v1 requires selector and unified_diff")
        selector = arguments["selector"]
        diff = arguments["unified_diff"]
        if not isinstance(selector, str) or not isinstance(diff, str):
            raise ValueError("patch_test_selector_v1 arguments must be strings")
        if (
            not selector
            or len(selector) > 500
            or any(character in selector for character in ";|&`$\n")
        ):
            raise ValueError("test selector contains unsafe characters")
        if not diff or len(diff.encode()) > 100_000:
            raise ValueError("unified diff is empty or oversized")
        return
    raise ValueError("unknown recipe arguments schema")
