# Agentic Engineering Lab

Agentic Engineering Lab is a local-first reference system for building and evaluating three constrained coding agents.

- A read-only repository scout produces grounded implementation plans.
- A pull-request risk assessor explains risk, required proof, and uncertainty.
- A CI fixer diagnoses failures and can update an opted-in pull-request branch only after deterministic safety gates pass.

The system is built for evidence, not demo theater. Every run records its pinned repository revision, model configuration, tool use, policy decisions, costs, latency, validations, and outcome.

## Scope

The first target is Mission Control. It is the only allowlisted repository during the initial evaluation cycle. The lab itself is public under Apache-2.0. Runtime services run locally with Docker Compose.

## Documentation

- [Product requirements](docs/PRD.md)
- [System architecture](docs/architecture.md)
- [Data model and state machine](docs/data-model.md)
- [API, webhook, and tool contracts](docs/contracts.md)
- [Repository execution manifest](docs/repository-manifest.md)
- [Security and policy specification](docs/security.md)
- [Evaluation specification](docs/evaluation.md)
- [Implementation plan](docs/implementation-plan.md)

## Architectural stance

FastAPI and PostgreSQL form the control plane. Pydantic AI supplies typed model and tool contracts. OpenRouter supplies model access. Langfuse Cloud provides private traces. Disposable credential-free Docker executors run repository commands. A single GitHub App is mediated entirely by a deterministic capability gateway.

Implementation follows the milestone sequence in [the implementation plan](docs/implementation-plan.md).

## Local development

1. Copy `.env.example` to `.env` and replace the placeholder secrets with local values.
2. Install the locked development environment with `uv sync --all-extras`.
3. Run the checks with `uv run ruff check .` and `uv run pytest`.
4. Start the local control plane with `docker compose up --build`.

The API is available only on `127.0.0.1:8000`. `GET /healthz` reports process liveness and `GET /readyz` verifies configuration plus database access.

## Implementation status

The control plane and Scout vertical slice are complete and verified with a live pinned run. Event routing, typed diff and check evidence, evaluation gates, disposable executor transport, fixed recipe adapters, patch policy, and the production GitHub branch writer have automated coverage. Thirty approved SHA-backed fixtures pin ten live pull requests and their failing checks. The published evaluation executor image passes reproduction, patch validation, and lint probes at its immutable digest. Candidate runs, held-out reviews, and an opted-in live patch remain gated work. See [the current milestone status](docs/implementation-plan.md#current-implementation-status) for exact evidence and blockers.
