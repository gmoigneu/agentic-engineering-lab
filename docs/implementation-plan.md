# Implementation plan

## Delivery protocol

Implement one milestone at a time. Do not begin a later milestone until the prior milestone acceptance checks pass and its documentation is updated. Each milestone requires unit tests, contract tests for changed boundaries, a migration when the database changes, and a manual local verification note in the pull request.

## Current implementation status

Verified on 2026-07-17.

| Milestone | State | Evidence and remaining gate |
| --- | --- | --- |
| 1. Lab foundation | Complete | Compose services are healthy, readiness passes, migrations are at head, and lease heartbeat plus reclaim behavior has integration coverage. |
| 2. Scout vertical slice | Complete | A live pinned Scout run succeeded with resolvable citations, actual StreamLake usage and billed cost, a released lease, and a retrievable private Langfuse trace. |
| 3. Evaluation baseline | Complete | Fixture validation, split isolation, exact five-case gates, scorecard export, and held-out review gates pass. Thirty approved `fixtures-v1` files pin ten live pull requests and their first completed failing checks for repository `1303663681`. |
| 4. Scout v1 and model comparison | Ready for execution | Three distinct model and provider pairs and ten Scout fixtures are approved. The comparison contract holds prompt, tools, manifest, run budget, tasks, evaluator, data collection, and fallback policy fixed while reporting candidate-specific pinned providers. Runs and reviews remain required. |
| 5. Event control plane | Complete | Verified routing, deduplication, supersession, causal links, allowlists, and audited snapshot reads have automated coverage. |
| 6. Pull-request risk assessor | Ready for execution | SHA-bound `DiffEvidenceV1`, audited gateway retrieval, the bound `inspect_diff` tool, and ten approved assessor fixtures have automated validation. Runs and reviews remain required. |
| 7. CI diagnosis | Ready for execution | `CheckEvidenceV1`, check output, annotation and GitHub Actions log adapters, typed executor transport, fixed recipe adapters, a hardened Docker runner, and ten approved CI fixtures have automated coverage. The published multi-architecture executor digest passed live reproduction, patch validation, and lint probes. Runs and reviews remain required. |
| 8. CI safe patching | Partial | Patch policy, opt-in, one-attempt guard, exact-SHA recheck, durable decisions, strict text patch application, and the production GitHub App Git-object writer have automated coverage. The CI patch tool loop and an explicitly opted-in live evaluation PR remain required. |
| 9. Held-out results | Blocked on release cycle | Held-out runs, manual reviews, frozen labels, and public redacted exports must come from the approved evaluation cycle. They must not be synthesized by the harness implementation. |

The automated suite currently contains 93 passing tests. Static checks, documentation links, Compose health, API readiness, PostgreSQL migration state, live OpenRouter execution, durable model economics, worker heartbeat renewal, private Langfuse retrieval, launcher Docker Engine access, the disposable executor boundary, deterministic repository seeding, fixture materialization, and published-image reproduction, patch validation, and lint have been verified. The first published-image probe exposed a Ruff cache permission failure. The replacement digest `sha256:3c77a98a70a2cead5c7c97da52a05e4fb68c99c7dadd4a5451e4e5b888ae944d` passed the corrected probe. The first Scout canary exposed citation coverage being checked after the configured repair opportunity. The run is excluded as a harness failure, and citation coverage now participates in typed output validation. The three approved model and provider endpoints and GitHub App installation for repository `1303663681` were verified read-only. The App grants Contents write as the only repository write permission.

The next evaluation tranche is the $6 Scout comparison across the five development fixtures and three approved model-provider pairs. No live GitHub write is authorized until one selected same-repository evaluation PR has a durable unexpired opt-in record.

## Milestone 1. Lab foundation

Create Python project metadata, lockfile, Docker Compose, FastAPI app, Pydantic Settings, PostgreSQL connection, SQLAlchemy models, Alembic baseline, health endpoints, local operator authentication, and service wiring. Add GitHub webhook HMAC verifier, event persistence, delivery deduplication, manual run endpoint, replay fixture endpoint, queue table, lease claimant, and minimal server-rendered run list.

Acceptance checks

- `docker compose up` starts API, worker, and PostgreSQL with readiness checks.
- Valid signed fixture creates one queued run. Replaying it creates no duplicate run.
- Invalid signature creates no run and records only safe rejection metadata.
- Worker acquires, heartbeats, expires, and reclaims a lease in integration tests.
- Inspector displays event, run ID, status, and transition history.

## Milestone 2. Scout vertical slice

Implement domain schemas for task input, claims, citations, scout artifact, budgets, tool call, model call, and terminal errors. Build typed snapshot-backed `list_tree`, `read_file`, `search_text`, `search_structure`, and `git_history` tools. Implement model gateway with OpenRouter provider policy, Pydantic AI output validation, one repair attempt, usage capture, and Langfuse correlation. Build redaction before model and trace export.

Acceptance checks

- A manual pinned Mission Control task produces schema-valid scout JSON and readable inspector view.
- Every material claim has a resolvable citation or is an explicit unknown.
- Tests prove no scout path can invoke GitHub write or executor launcher.
- Langfuse trace links to the run ID without exposing unredacted fixture secret data.
- Budget exhaustion and invalid final output become terminal recorded outcomes.

## Milestone 3. Evaluation baseline

Create versioned fixture format, development and held-out directories, evaluator registry, deterministic scout evaluators, batch runner, review form, and scorecard export. Add five development and five held-out scout fixtures before prompt iteration. Record OpenRouter billed cost, provider, and stage timings.

Acceptance checks

- Fixture validation rejects labels that lack pinned SHA, rubric, or deterministic checks.
- Held-out scoring keys are unavailable to agent execution tests.
- Batch export includes all required configuration and terminal outcome fields.
- Human review entry is required for held-out batch completion.

## Milestone 4. Scout v1 and model comparison

Complete scout plan schema and run the three pinned candidate classes on the identical development set, then once on held-out set. Fix harness defects before treating results as model differences. Select a scout default only from recorded metrics.

Acceptance checks

- All candidates use identical manifest, prompt, tool definitions, budget, provider policy, and evaluator versions.
- Report distinguishes infrastructure failure, model failure, policy refusal, and evaluator failure.
- A scorecard documents limitations and no global-winner claim.

## Milestone 5. Event control plane

Add verified `pull_request` and completed failing `check_run` routing, PR and SHA supersession, causal chain records, target allowlist, and replay fixtures. Build capability gateway read adapters with policy decision records.

Acceptance checks

- Only approved event actions create the stated role run.
- New human head SHA supersedes old active work.
- Bot retry events do not start a second repair loop.
- All GitHub reads pass through gateway contract tests.

## Milestone 6. Pull-request risk assessor

Implement scout-map consumption, diff and history adapters, risk artifact, evidence coverage evaluator, unavailable-signal handling, and five plus five assessor cases.

Acceptance checks

- Assessor cannot run executor recipes or write GitHub data.
- Risk output without evidence coverage is rejected.
- Held-out review records calibration, false alarms, and missed high-risk changes.

## Milestone 7. CI diagnosis

Implement failure taxonomy, check and log adapters, lab-owned manifest registry, credential-free snapshot creation, executor launcher, recipe adapters, diagnosis artifact, refusal contract, and five plus five CI cases. Keep GitHub write disabled in this milestone.

Acceptance checks

- Executor lacks GitHub, OpenRouter, Langfuse, Docker socket, and host-secret access.
- Recipe adapter accepts validated named arguments only.
- Network default is disabled and tested.
- External, flaky, permission, secret, and infrastructure failures refuse with evidence.

## Milestone 8. CI safe patching

Implement unified-diff parsing, source-only path policy, secret scan, patch precheck, post-application validation, opt-in registry, one-attempt guard, exact-SHA recheck, and gateway apply operation. Enable it only for explicitly opted-in evaluation PRs.

Acceptance checks

- Tests reject protected-path, test, workflow, migration, lockfile, authorization, binary, symlink, and stale-head patches.
- A passing safe source patch updates only the existing same-repository PR branch.
- A changed head SHA, missing opt-in, failed validation, or secret detection produces no GitHub write.
- The gateway records every allow and deny decision.

## Milestone 9. Held-out results and series artifacts

Run held-out batches, complete human review, calibrate any judge, freeze task labels and configuration, and export scorecards, trace excerpts, failure examples, and reproducibility metadata for Episodes 3 through 7.

Acceptance checks

- Every published number is traceable to a batch export and run IDs.
- Public excerpts are redacted and do not expose a live trace project.
- The final report states task count, split, repository scope, model and provider configuration, limitations, failures, and refusals.
