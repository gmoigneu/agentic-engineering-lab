# Data model and state machine

## Persistence rules

PostgreSQL is authoritative. Store append-only event and transition records. Mutable run summary columns exist for efficient inspection but must agree with the transition history. Store large redacted artifacts in the database for v1 unless a later size threshold requires local object storage.

## Core tables

| Table | Required fields | Purpose |
| --- | --- | --- |
| `webhook_events` | id, delivery_id, event_name, repository_id, payload_hash, received_at, signature_valid | Immutable accepted or rejected delivery record |
| `runs` | id, role, source, repository_id, pull_number, pinned_sha, status, manifest_version, policy_version, prompt_hash, model_config, budget, created_at, terminal_at | Run aggregate and query surface |
| `run_transitions` | id, run_id, from_status, to_status, reason_code, actor, occurred_at, metadata | Append-only state history |
| `run_leases` | run_id, worker_id, acquired_at, heartbeat_at, expires_at, attempt | Durable worker ownership |
| `artifacts` | id, run_id, kind, schema_version, content_json, content_hash, redaction_state, created_at | Canonical typed outputs and summaries |
| `citations` | id, artifact_id, claim_id, source_kind, locator, pinned_sha, excerpt_hash | Machine-resolvable evidence |
| `tool_calls` | id, run_id, sequence, tool_name, request_json, result_summary, status, duration_ms, policy_decision_id | Auditable capability use |
| `model_calls` | id, run_id, sequence, model_id, provider, settings, usage, billed_cost, latency_ms, langfuse_trace_id | Model outcome and economics |
| `policy_decisions` | id, run_id, policy_name, input_hash, outcome, reason_code, metadata, occurred_at | Allow or deny proof |
| `evaluations` | id, run_id, dataset_split, evaluator_version, score_json, passed, created_at | Deterministic and model-judge scores |
| `human_reviews` | id, run_id, reviewer, outcome, minutes, disposition, missing_evidence, notes, created_at | Review burden and calibration data |
| `target_manifests` | id, repository_id, version, content, content_hash, approved_at, retired_at | Lab-owned execution policy |
| `pull_request_opt_ins` | repository_id, pull_number, enabled_at, enabled_by, expires_at, reason | Required CI write permission |
| `run_causal_links` | id, source_run_id, target_run_id, relation, created_at | Supersession and event-chain evidence |
| `redaction_events` | id, run_id, detector_name, content_hash, source_locator, resolution_state, created_at | Secret-detection evidence without detected values |
| `webhook_run_links` | webhook_event_id, run_id | Exact event-to-run traceability |

Use UUID primary keys. Use UTC timestamps. Use JSONB only for versioned typed payloads whose Pydantic schema is stored in code. Index delivery ID, run status, repository plus pinned SHA, pull request plus pinned SHA, lease expiry, and trace ID.

## Run status machine

| Status | Meaning | Allowed next status |
| --- | --- | --- |
| `received` | Intake validation has started | `rejected`, `queued` |
| `queued` | Durable job awaits a worker | `leased`, `cancelled`, `superseded` |
| `leased` | Worker owns the run | `snapshotting`, `running`, `cancelled`, `superseded`, `failed` |
| `snapshotting` | Gateway fetches pinned GitHub data or source | `running`, `refused`, `superseded`, `failed` |
| `running` | Agent loop or deterministic analysis is active | `evaluating`, `refused`, `budget_exhausted`, `failed`, `superseded` |
| `evaluating` | Output, patch, and validations are being checked | `ready_to_push`, `succeeded`, `refused`, `failed`, `superseded` |
| `ready_to_push` | CI patch passed all pre-push checks | `pushing`, `refused`, `superseded` |
| `pushing` | Gateway performs exact-SHA recheck and GitHub update | `succeeded`, `refused`, `failed` |
| `succeeded` | Terminal successful artifact or controlled push | none |
| `refused` | Terminal safe refusal with evidence | none |
| `rejected` | Terminal invalid or unauthorized intake | none |
| `budget_exhausted` | Terminal budget stop with evidence | none |
| `superseded` | Terminal replacement by a newer human head SHA | none |
| `cancelled` | Terminal operator cancellation | none |
| `failed` | Terminal unexpected control-plane failure | none |

Only the run service may transition status. Every transition validates the allowed-next-status list, records an actor, and emits a transition record. Terminal status is immutable.

## Artifact contracts

All artifacts include `schema_version`, `run_id`, `role`, `pinned_sha`, `created_at`, `claims`, `unknowns`, and `citations`. Claims include stable IDs so evaluators can assess citation coverage. Citations refer to immutable source locators such as `path#L10-L24`, `commit#sha`, `diff#file:hunk`, `check_run#id:line-range`, or `tool_result#call-id`.

The patch artifact includes base SHA, unified diff, changed paths, patch hash, named reproduction recipe, named validation recipe, exit codes, redacted output summary, and policy result. The control plane rejects a patch that lacks any required field.
