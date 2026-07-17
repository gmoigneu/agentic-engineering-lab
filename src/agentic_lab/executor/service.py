from __future__ import annotations

import secrets
from typing import Any

from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from agentic_lab.config.settings import Settings, get_settings
from agentic_lab.executor.launcher import ContainerRunner, default_docker_runner, launch_recipe
from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest
from agentic_lab.tools.snapshot import RepositorySnapshot


class RecipeLaunchPayload(BaseModel):
    manifest: ExecutionManifest
    run_id: str = Field(min_length=1, max_length=255)
    source_sha: str = Field(min_length=40, max_length=64)
    recipe_name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    snapshot_files: dict[str, str] = Field(max_length=20_000)

    @field_validator("snapshot_files")
    @classmethod
    def bounded_snapshot(cls, value: dict[str, str]) -> dict[str, str]:
        if sum(len(content.encode()) for content in value.values()) > 100_000_000:
            raise ValueError("executor snapshot exceeds the transport size limit")
        return value


def create_app(
    settings: Settings | None = None,
    runner: ContainerRunner | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    runner = runner or default_docker_runner(
        settings.executor_transport_root,
        settings.executor_host_transport_root,
    )
    app = FastAPI(title="Agentic Engineering Lab executor launcher")

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/recipes:run")
    def run_recipe(
        payload: RecipeLaunchPayload,
        x_operator_token: str | None = Header(default=None),
    ) -> dict[str, object]:
        configured = settings.operator_token.get_secret_value()
        if x_operator_token is None or not secrets.compare_digest(x_operator_token, configured):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="operator authentication required",
            )
        if payload.manifest.repository_id not in settings.allowed_repository_ids:
            raise HTTPException(status_code=403, detail="repository is not allowlisted")
        recipe = payload.manifest.recipes.get(payload.recipe_name)
        if recipe is None:
            raise HTTPException(status_code=422, detail="unknown manifest recipe")
        if settings.executor_image_digest is None or recipe.image != settings.executor_image_digest:
            raise HTTPException(status_code=422, detail="recipe image is not the configured digest")
        snapshot = RepositorySnapshot(payload.source_sha, payload.snapshot_files)
        return launch_recipe(
            runner,
            payload.manifest,
            RecipeRequest(
                payload.run_id,
                payload.source_sha,
                payload.recipe_name,
                payload.arguments,
            ),
            snapshot,
        )

    return app


app = create_app()
