import json
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path

from agentic_lab.executor.transport import RecipeExecutionResult
from agentic_lab.tools.snapshot import RepositorySnapshot

_PROBE = run_path("scripts/probe_evaluation_executor.py", run_name="probe_module")
probe = _PROBE["probe"]


class Runner:
    def run(self, spec, request, snapshot):  # type: ignore[no-untyped-def]
        assert spec.environment == {}
        assert spec.network == "none"
        assert snapshot.pinned_sha == request.source_sha
        exit_code = 1 if request.recipe_name == "reproduce" else 0
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
            exit_code=exit_code,
            stdout_hash="a" * 64,
            stderr_hash="b" * 64,
            stdout_excerpt="",
            stderr_excerpt="",
        )


def test_probe_requires_expected_reproduction_patch_and_lint_outcomes(tmp_path: Path) -> None:
    image = "ghcr.io/gmoigneu/agentic-lab-eval-executor@sha256:" + "a" * 64
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": "eval-v1",
                "repository_id": 1303663681,
                "repository": "gmoigneu/agentic-engineering-lab-eval",
                "allowed_source_paths": ["src/eval_service/*.py"],
                "protected_paths": ["tests/**"],
                "recipes": {
                    "reproduce": {
                        "kind": "reproduce",
                        "image": image,
                        "adapter": "pytest_v1",
                        "working_directory": "/work/workspace",
                        "arguments_schema": "test_selector_v1",
                        "timeout_seconds": 120,
                        "network": "none",
                    },
                    "validate_patch": {
                        "kind": "validate",
                        "image": image,
                        "adapter": "pytest_after_patch_v1",
                        "working_directory": "/work/workspace",
                        "arguments_schema": "patch_test_selector_v1",
                        "timeout_seconds": 120,
                        "network": "none",
                    },
                    "lint": {
                        "kind": "validate",
                        "image": image,
                        "adapter": "ruff_check_v1",
                        "working_directory": "/work/workspace",
                        "arguments_schema": "none_v1",
                        "timeout_seconds": 120,
                        "network": "none",
                    },
                },
            }
        )
    )
    fixture = tmp_path / "fixture.json"
    fixture.write_text(
        json.dumps(
            {
                "case_id": "ci-dev-01",
                "role": "ci",
                "fixture_revision": "fixtures-v1",
                "repository_id": 1303663681,
                "base_sha": "b" * 40,
                "pinned_sha": "a" * 40,
                "pull_request_number": 1,
                "check_run_id": 2,
                "task_input": "fix pagination",
                "source_provenance": "approved fixture",
                "expected_evidence": ["pagination.py"],
                "deterministic_assertions": ["reproduce"],
                "human_rubric": "minimal fix",
                "split": "development",
            }
        )
    )

    result = probe(
        manifest,
        fixture,
        tmp_path,
        runner=Runner(),
        snapshot_loader=lambda _path, sha: RepositorySnapshot(
            sha, {"src/eval_service/pagination.py": "value = 1\n"}
        ),
    )

    assert result["status"] == "passed"
    assert result["reproduce_exit_code"] == 1
    assert result["validate_patch_exit_code"] == 0
    assert result["lint_exit_code"] == 0
