from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Recipe(BaseModel):
    kind: str
    image: str
    working_directory: str
    arguments_schema: str
    timeout_seconds: int = Field(gt=0, le=3600)
    network: str

    @field_validator("image")
    @classmethod
    def immutable_image(cls, value: str) -> str:
        if "@sha256:" not in value:
            raise ValueError("recipe image must use an immutable digest")
        return value

    @field_validator("network")
    @classmethod
    def network_disabled(cls, value: str) -> str:
        if value != "none":
            raise ValueError("v1 recipes must disable network access")
        return value


class ExecutionManifest(BaseModel):
    manifest_version: str
    repository_id: int
    repository: str
    allowed_source_paths: list[str]
    protected_paths: list[str]
    recipes: dict[str, Recipe]


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
    if "command" in request.arguments or "shell" in request.arguments:
        raise ValueError("recipe arguments cannot contain command text")
    return recipe
