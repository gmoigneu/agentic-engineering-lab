from datetime import UTC, datetime

from fastapi.testclient import TestClient

from agentic_lab.config.settings import Settings
from agentic_lab.executor.service import create_app
from agentic_lab.executor.transport import RecipeExecutionResult


class Runner:
    calls = 0

    def run(self, spec, request, snapshot):  # type: ignore[no-untyped-def]
        self.calls += 1
        assert spec.environment == {}
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


def test_executor_api_requires_operator_auth_allowlist_and_exact_image_digest() -> None:
    image = "executor@sha256:" + "a" * 64
    settings = Settings(
        operator_token="operator",
        github_webhook_secret="webhook",
        allowed_repository_ids=frozenset({1}),
        executor_image_digest=image,
    )
    runner = Runner()
    client = TestClient(create_app(settings, runner))
    payload = {
        "manifest": {
            "manifest_version": "v1",
            "repository_id": 1,
            "repository": "owner/repo",
            "allowed_source_paths": ["src/**"],
            "protected_paths": [],
            "recipes": {
                "validate": {
                    "kind": "validate",
                    "image": image,
                    "adapter": "noop_v1",
                    "working_directory": "/work/workspace",
                    "arguments_schema": "none_v1",
                    "timeout_seconds": 10,
                    "network": "none",
                }
            },
        },
        "run_id": "run-1",
        "source_sha": "d" * 40,
        "recipe_name": "validate",
        "arguments": {},
        "snapshot_files": {"src/app.py": "value = 1\n"},
    }

    assert client.post("/v1/recipes:run", json=payload).status_code == 401
    response = client.post(
        "/v1/recipes:run",
        json=payload,
        headers={"X-Operator-Token": "operator"},
    )

    assert response.status_code == 200
    assert response.json()["exit_code"] == 0
    assert runner.calls == 1
