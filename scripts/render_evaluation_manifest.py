from __future__ import annotations

import argparse
from pathlib import Path

from agentic_lab.executor.manifest import ExecutionManifest


def render(image: str, destination: Path) -> ExecutionManifest:
    manifest = ExecutionManifest.model_validate(
        {
            "manifest_version": "eval-v1",
            "repository_id": 1303663681,
            "repository": "gmoigneu/agentic-engineering-lab-eval",
            "allowed_source_paths": ["src/eval_service/*.py"],
            "protected_paths": [
                ".github/**",
                "tests/**",
                "pyproject.toml",
                "uv.lock",
                "src/eval_service/records.py",
            ],
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
            "redaction_patterns": [],
            "budgets": {
                "max_model_turns": 8,
                "max_tool_calls": 24,
                "max_wall_seconds": 300,
                "max_usd": 0.2,
            },
        }
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evaluation/manifests/eval-v1.json"),
    )
    arguments = parser.parse_args()
    manifest = render(arguments.image, arguments.output)
    print(f"Rendered {manifest.manifest_version} to {arguments.output}")


if __name__ == "__main__":
    main()
