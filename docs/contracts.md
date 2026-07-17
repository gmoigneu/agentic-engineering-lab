# API, webhook, and tool contracts

## HTTP API

All API responses contain `request_id`. The inspector endpoints are local-only in v1. Mutating endpoints require an operator token from local configuration.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/webhooks/github` | Verify and persist GitHub delivery |
| `POST` | `/v1/runs` | Create a manual scout or replay run |
| `POST` | `/v1/runs/{run_id}/cancel` | Cancel a queued or leased run |
| `GET` | `/v1/runs/{run_id}` | Retrieve typed run summary and links |
| `GET` | `/v1/runs/{run_id}/artifacts/{kind}` | Retrieve a canonical artifact |
| `POST` | `/v1/runs/{run_id}/review` | Store human-review record |
| `POST` | `/v1/replays/github` | Submit stored signed fixture through intake path |
| `GET` | `/` | Server-rendered run list |
| `GET` | `/runs/{run_id}` | Server-rendered run detail |
| `GET` | `/healthz` | Process liveness |
| `GET` | `/readyz` | Database and configuration readiness |

Manual run input requires role, repository ID, pinned SHA, task text, and optional evaluation case ID. The service rejects a repository outside the allowlist, a mutable ref, an unknown role, missing manifest, or a budget over the configured maximum.

## GitHub webhook intake

Verify `X-Hub-Signature-256` against the raw request body with constant-time comparison. Persist only after verification. Record rejected signature attempts with payload hash and no raw payload. Handle only `pull_request` actions `opened`, `synchronize`, and `reopened`, plus completed failing `check_run` events. Ignore all other events with a recorded reason.

For pull-request events, queue the assessor only when the head SHA is available. For check-run events, queue CI diagnosis only when conclusion is failure, repository is allowlisted, the PR association resolves to a same-repository branch, and the event is not a bot retry for the same human head SHA. A later human head SHA supersedes older work.

## Capability gateway

The gateway is the only code that uses the GitHub App private key or installation token. It mints a short-lived token scoped to one allowed repository and only the permissions required by an operation. Every method takes `run_id` and records a policy decision before work begins.

| Gateway operation | Roles | Preconditions |
| --- | --- | --- |
| Fetch repository archive at SHA | Scout, assessor, CI | Allowlisted repository and immutable SHA |
| Read file, tree, or commit | Scout, assessor, CI | Corresponding read policy and pinned source |
| Read typed pull-request diff | Assessor, CI | Bound pull request and exact head SHA |
| Read typed check, annotation, or log | CI | Bound check run and exact head SHA |
| Create source snapshot | CI | Pinned SHA and approved manifest |
| Apply validated patch to PR head branch | CI only | All push-gate conditions and opt-in entry |

The gateway never exposes a generic REST client to agent code. Methods return typed data transfer objects with source locator and redaction metadata.

`DiffEvidenceV1` records repository and pull-request identity, immutable base and head SHAs, same-repository state, the head branch, typed file status, previous and current path, line counts, binary, symlink, and submodule state, patch hash, bounded hunks, content hashes, truncation, and redaction state.

`CheckEvidenceV1` records repository and check-run identity, immutable head SHA, status, conclusion, app identity, timestamps, bounded check output, typed annotations, bounded GitHub Actions log excerpts when available, content hashes, truncation, redaction state, and explicit unavailable signals. Full logs require the GitHub App Actions read permission. Missing permission produces unavailable evidence and never widens access.

## Model gateway

Every request includes run ID, role, pinned model ID, provider allowlist, `data_collection` deny, prompt hash, tool definitions hash, and remaining budget. Evaluation requests disable fallback. Store the actual provider returned by OpenRouter. Reject latest aliases and unknown provider configuration. Pass the run ID to Langfuse correlation metadata.

The model gateway exposes only `run_agent_loop`. It accepts a role-specific system prompt, typed task input, tool registry, output schema, and budget. It returns typed final output or a typed terminal error. A final-output schema failure receives one repair request with validation errors only. A second failure is terminal.

## Tool contracts

Every tool request is Pydantic-validated before execution. Invalid requests return a typed contract error and consume one tool-call budget unit. Tool output is redacted before it reaches the model and carries an untrusted-source marker.

| Tool | Roles | Input | Output | Side effect |
| --- | --- | --- | --- | --- |
| `list_tree` | Scout, assessor, CI | path prefix and depth | paths, object types, pinned SHA | None |
| `read_file` | Scout, assessor, CI | path and line window | text, locator, content hash | None |
| `search_text` | Scout, assessor, CI | literal or regex query and path scope | matches, locators, truncation state | None |
| `search_structure` | Scout, assessor, CI | ast-grep rule and language scope | structural matches and locators | None |
| `git_history` | Scout, assessor, CI | path or symbol scope and limit | commits and locators | None |
| `inspect_diff` | Assessor, CI | PR number or base and head SHA | typed file and hunk summary | None |
| `inspect_check` | CI | check-run ID | conclusion, annotations, redacted logs | None |
| `run_recipe` | CI | manifest recipe name and arguments schema | exit code, duration, redacted artifacts | Disposable executor |
| `propose_patch` | CI | unified diff and base SHA | patch artifact and policy precheck | None |

The model cannot call `git`, `ripgrep`, `ast-grep`, Docker, HTTP, or shell directly. Python adapters implement the tools behind the contract. `run_recipe` accepts only an exact recipe name defined by the lab-owned manifest. It does not accept command text.

## Executor transport

The launcher accepts `RecipeRequestV1` with run ID, source SHA, manifest version, recipe name, adapter ID, validated arguments, immutable image digest, timeout, and expected artifacts. It materializes source files read-only, mounts the typed request read-only, and gives the child only an ephemeral workspace and output directory.

The child runs with no network, a read-only root filesystem, all capabilities dropped, no-new-privileges, bounded CPU, memory, process count, and time. The launcher injects no environment values. `RecipeResultV1` repeats the request identity and includes timestamps, exit code, stdout and stderr hashes, bounded redacted excerpts, artifact paths, sizes, and hashes. The launcher rejects an identity mismatch, missing artifact, symlink, size mismatch, or hash mismatch.

V1 adapters are `noop_v1`, `pytest_v1`, `pytest_after_patch_v1`, and `ruff_check_v1`. Each maps an approved arguments schema to a fixed argv tuple. The patch-validation adapter first applies the supplied bounded unified diff inside the disposable workspace, then runs its fixed pytest selector. No adapter accepts command, shell, or script text.

## GitHub branch writer

The production writer requests a repository-scoped installation token with Contents write and Metadata read only. It rechecks the branch head, applies the validated text patch against exact base content, creates Git blobs, a tree, and a commit containing the run ID, then performs a non-force ref update. It cannot create pull requests, comments, checks, workflows, releases, or default-branch updates.

## CI push gate

`apply_validated_patch` must re-evaluate all conditions immediately before it writes.

- The PR appears in `pull_request_opt_ins` and opt-in has not expired.
- The head repository equals the base repository and head SHA equals the run pinned SHA.
- The base SHA of the patch equals the pinned SHA and the unified diff applies cleanly.
- Failure classification is repository-caused and reproduction passed.
- At least one relevant manifest validation recipe passed after the patch.
- Changed paths are application-source paths allowed by the manifest.
- No changed path is a test, CI workflow, migration, dependency manifest, lockfile, authentication or authorization path, infrastructure path, secret path, or protected path.
- Secret scan, patch policy, budget policy, and one-attempt policy passed.

Any failed predicate records a deny decision and transitions the run to `refused` or `superseded`. The gateway never attempt a rebase.
