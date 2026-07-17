# Repository execution manifest

## Purpose

The manifest is the lab-owned execution contract for one target repository. It defines what the CI executor may prepare, validate, and modify. It is versioned in this repository, approved by a human, copied into `target_manifests`, and selected before a run starts.

The target repository and its pull requests never define or override this manifest.

## Required policy

- Identify target repository by immutable GitHub repository ID and canonical full name.
- Define allowed application-source path globs.
- Define protected path globs.
- Define named setup, reproduction, and validation recipes.
- Define each recipe image, working directory, argument schema, timeout, required local service names, and expected output artifacts.
- Define a redaction pattern set in addition to global secret detection.
- Define maximum model and executor budgets within global ceilings.
- Keep egress disabled by default. A v1 manifest may not grant external egress.

## Example shape

```toml
manifest_version = "1"
repository_id = 123456
repository = "owner/mission-control"
allowed_source_paths = ["backend/**/*.py", "frontend/**/*.{ts,tsx}"]
protected_paths = [".github/**", "**/*_test.py", "**/*.test.ts", "migrations/**", "package-lock.json", "poetry.lock"]

[budgets]
max_model_turns = 12
max_tool_calls = 40
max_wall_seconds = 1200
max_usd = 3.00

[recipes.reproduce_failing_test]
kind = "reproduce"
image = "ghcr.io/example/mission-control-executor@sha256:REPLACE"
adapter = "pytest_v1"
working_directory = "/work/workspace"
arguments_schema = "test_selector_v1"
timeout_seconds = 600
network = "none"

[recipes.backend_targeted_test]
kind = "validate"
image = "ghcr.io/example/mission-control-executor@sha256:REPLACE"
adapter = "pytest_v1"
working_directory = "/work/workspace"
arguments_schema = "test_selector_v1"
timeout_seconds = 600
network = "none"
```

This example is illustrative. A real manifest must use an immutable image digest and a stable argument schema. Recipes must produce machine-readable result metadata even when the underlying test command fails.

## Recipe execution

The executor launcher validates manifest version, recipe name, adapter identity, argument schema, and exact configured image digest. It materializes a read-only source snapshot and request, creates an ephemeral writable workspace, starts the declared image without network or injected environment values, and collects output from `/work/output`. It does not interpolate model-provided strings into shell commands. A recipe adapter maps validated arguments to a fixed argv tuple.

Recipe output includes run ID, recipe name, image digest, source SHA, start and finish timestamps, exit code, stdout and stderr hashes, redacted excerpts, structured test results when available, and artifact paths. The launcher rejects output from another run ID or source SHA.
