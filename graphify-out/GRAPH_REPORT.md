# Graph Report - agentic-engineering-lab  (2026-07-17)

## Corpus Check
- 165 files · ~53,254 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 886 nodes · 2169 edges · 59 communities (48 shown, 11 thin omitted)
- Extraction: 59% EXTRACTED · 41% INFERRED · 0% AMBIGUOUS · INFERRED: 879 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `05cb5f92`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- RepositorySnapshot
- Run
- SnapshotToolRegistry
- AgentRole
- push_validated_patch
- ValueError
- EvaluationCase
- TraceExporter
- LeaseHeartbeat
- What You Must Do When Invoked
- Settings
- PolicyOutcome
- Product requirements document
- Implementation plan
- graphify reference: extra exports and benchmark
- System architecture
- API, webhook, and tool contracts
- Evaluation specification
- Security and policy specification
- Implementation rules
- graphify reference: query, path, explain
- Data model and state machine
- Repository execution manifest
- Agentic Engineering Lab
- store_evaluation
- graphify reference: add a URL and watch a folder
- graphify reference: commit hook and native CLAUDE.md integration
- graphify reference: incremental update and cluster-only
- build_session_factory
- graphify reference: GitHub clone and cross-repo merge
- graphify reference: transcribe video and audio
- extraction-spec.md
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- agentic-engineering-lab
- README.md
- ValueError
- seed

## God Nodes (most connected - your core abstractions)
1. `RepositorySnapshot` - 68 edges
2. `AgentRole` - 64 edges
3. `RunSource` - 44 edges
4. `RunStatus` - 44 edges
5. `SnapshotToolRegistry` - 44 edges
6. `Run` - 34 edges
7. `RunCreate` - 29 edges
8. `ModelBudget` - 27 edges
9. `transition_run()` - 27 edges
10. `PolicyOutcome` - 26 edges

## Surprising Connections (you probably didn't know these)
- `test_failed_check_routes_to_ci()` --calls--> `_queue_check_run()`  [INFERRED]
  tests/unit/test_webhook_routing.py → src/agentic_lab/api/app.py
- `test_worker_builds_private_langfuse_trace_exporter()` --calls--> `Settings`  [INFERRED]
  tests/unit/test_worker_dependencies.py → src/agentic_lab/config/settings.py
- `test_worker_builds_the_narrow_github_app_writer_only_in_the_trusted_process()` --calls--> `Settings`  [INFERRED]
  tests/unit/test_worker_dependencies.py → src/agentic_lab/config/settings.py
- `test_worker_provider_requires_key_and_pinned_model()` --calls--> `Settings`  [INFERRED]
  tests/unit/test_worker_dependencies.py → src/agentic_lab/config/settings.py
- `test_invalid_signature_records_safe_metadata_without_a_run()` --indirect_call--> `WebhookEvent`  [INFERRED]
  tests/integration/test_intake_and_leases.py → src/agentic_lab/db/models.py

## Import Cycles
- None detected.

## Communities (59 total, 11 thin omitted)

### Community 0 - "RepositorySnapshot"
Cohesion: 0.05
Nodes (40): CapabilityAuditPort, CapabilityGateway, GitHubReadPort, Protocol, Role-gated facade. It deliberately has no generic REST method or write method., GitHubAppInstallationAuth, Client, bounded_untrusted_text() (+32 more)

### Community 1 - "Run"
Cohesion: 0.06
Nodes (105): DeclarativeBase, LookupError, _detail(), _queue_check_run(), _queue_webhook_run(), _summary(), Base, Artifact (+97 more)

### Community 2 - "SnapshotToolRegistry"
Cohesion: 0.07
Nodes (67): AsyncClient, ModelHTTPError, OpenAIChatModel, UUID, run_assessor(), run_ci_diagnosis(), UUID, run_scout() (+59 more)

### Community 3 - "AgentRole"
Cohesion: 0.09
Nodes (18): LangfuseClient, LangfuseTraceSink, Any, Protocol, Match Langfuse's deterministic W3C trace-ID derivation., trace_id_for_run(), TraceExportResult, TraceSink (+10 more)

### Community 4 - "push_validated_patch"
Cohesion: 0.09
Nodes (33): main(), Path, render(), apply_validated_patch(), GitHubBranchWriter, Protocol, Narrow port implemented only by the trusted GitHub App adapter., Sole write path. It rechecks the head SHA after policy evaluation. (+25 more)

### Community 5 - "ValueError"
Cohesion: 0.06
Nodes (58): _execute(), main(), probe(), Path, _run(), _snapshot_at(), SnapshotLoader, _apply_workspace_diff() (+50 more)

### Community 6 - "EvaluationCase"
Cohesion: 0.07
Nodes (40): BatchBudget, BatchConfiguration, CaseResult, _cost_per_success(), export_scorecard(), _failure_rate(), held_out_complete(), load_cases() (+32 more)

### Community 7 - "TraceExporter"
Cohesion: 0.27
Nodes (9): Runner, _collect_check(), _fixture(), _load_seed(), main(), materialize(), Path, Path (+1 more)

### Community 8 - "LeaseHeartbeat"
Cohesion: 0.16
Nodes (9): LeaseHeartbeat, LeaseLostError, Any, RuntimeError, Renew one durable lease while its worker attempt is active., _claimed_run(), _sessions(), test_heartbeat_renews_lease_during_long_work() (+1 more)

### Community 9 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 11 - "Settings"
Cohesion: 0.06
Nodes (35): BaseSettings, create_app(), _effective_budget(), _process_github_delivery(), FastAPI, Session, sessionmaker, _record_invalid_delivery() (+27 more)

### Community 12 - "PolicyOutcome"
Cohesion: 0.29
Nodes (6): build_refusal(), classify_failure(), UUID, Conservative classification. Ambiguous logs never enable patching., requires_refusal(), test_failure_taxonomy_is_conservative()

### Community 13 - "Product requirements document"
Cohesion: 0.25
Nodes (7): Goals, Non-goals for v1, Product acceptance, Product requirements document, Product statement, Success measures, Users and jobs

### Community 14 - "Implementation plan"
Cohesion: 0.17
Nodes (12): Current implementation status, Delivery protocol, Implementation plan, Milestone 1. Lab foundation, Milestone 2. Scout vertical slice, Milestone 3. Evaluation baseline, Milestone 4. Scout v1 and model comparison, Milestone 5. Event control plane (+4 more)

### Community 15 - "graphify reference: extra exports and benchmark"
Cohesion: 0.22
Nodes (8): graphify reference: extra exports and benchmark, Step 6b - Wiki (only if --wiki flag), Step 7 - Neo4j export (only if --neo4j or --neo4j-push flag), Step 7a - FalkorDB export (only if --falkordb or --falkordb-push flag), Step 7b - SVG export (only if --svg flag), Step 7c - GraphML export (only if --graphml flag), Step 7d - MCP server (only if --mcp flag), Step 8 - Token reduction benchmark (only if total_words > 5000)

### Community 16 - "System architecture"
Cohesion: 0.22
Nodes (9): Components, Configuration, Control flow, Dependency direction, Design principles, Failure handling, Local topology, Module layout (+1 more)

### Community 17 - "API, webhook, and tool contracts"
Cohesion: 0.22
Nodes (9): API, webhook, and tool contracts, Capability gateway, CI push gate, Executor transport, GitHub branch writer, GitHub webhook intake, HTTP API, Model gateway (+1 more)

### Community 18 - "Evaluation specification"
Cohesion: 0.25
Nodes (7): Case design, Dataset structure, Evaluation specification, Evaluators, Metrics, Model comparison protocol, Reporting

### Community 19 - "Security and policy specification"
Cohesion: 0.25
Nodes (7): Audit and incident response, Authoritative inputs, Credential policy, Patch policy, Redaction policy, Security and policy specification, Trust boundaries

### Community 21 - "Implementation rules"
Cohesion: 0.33
Nodes (5): Delivery bar, graphify, Implementation rules, Non-negotiable rules, Working conventions

### Community 22 - "graphify reference: query, path, explain"
Cohesion: 0.33
Nodes (5): For /graphify explain, For /graphify path, graphify reference: query, path, explain, Step 0 — Constrained query expansion (REQUIRED before traversal), Step 1 — Traversal

### Community 23 - "Data model and state machine"
Cohesion: 0.33
Nodes (5): Artifact contracts, Core tables, Data model and state machine, Persistence rules, Run status machine

### Community 24 - "Repository execution manifest"
Cohesion: 0.33
Nodes (5): Example shape, Purpose, Recipe execution, Repository execution manifest, Required policy

### Community 25 - "Agentic Engineering Lab"
Cohesion: 0.33
Nodes (6): Agentic Engineering Lab, Architectural stance, Documentation, Implementation status, Local development, Scope

### Community 26 - "store_evaluation"
Cohesion: 0.33
Nodes (6): CI fixer, Functional requirements, Observability and review, Risk assessor, Run intake, Scout

### Community 27 - "graphify reference: add a URL and watch a folder"
Cohesion: 0.50
Nodes (3): For /graphify add, For --watch, graphify reference: add a URL and watch a folder

### Community 28 - "graphify reference: commit hook and native CLAUDE.md integration"
Cohesion: 0.50
Nodes (3): For git commit hook, For native CLAUDE.md integration, graphify reference: commit hook and native CLAUDE.md integration

### Community 29 - "graphify reference: incremental update and cluster-only"
Cohesion: 0.50
Nodes (3): For --cluster-only, For --update (incremental re-extraction), graphify reference: incremental update and cluster-only

### Community 31 - "build_session_factory"
Cohesion: 0.40
Nodes (4): Answer, Outcome, Q: What is missing from the implementation plan and which tasks remain?, Source Nodes

### Community 57 - "README.md"
Cohesion: 0.29
Nodes (5): Approval gate, Development split, Evaluation fixture plan v1, Held-out split, Evaluation fixture approval

### Community 59 - "ValueError"
Cohesion: 0.05
Nodes (31): _immutable_sha(), _contains_command_key(), ManifestBudgets, Any, BaseModel, Recipe, _validate_arguments(), validate_recipe_request() (+23 more)

### Community 62 - "seed"
Cohesion: 0.40
Nodes (8): main(), Path, _run(), seed(), _write(), _materialize(), Path, test_seed_base_passes_and_every_scenario_has_one_failing_check()

## Knowledge Gaps
- **116 isolated node(s):** `agentic-engineering-lab`, `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)`, `Step 1 - Ensure graphify is installed` (+111 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentRole` connect `Run` to `RepositorySnapshot`, `SnapshotToolRegistry`, `EvaluationCase`, `TraceExporter`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `RepositorySnapshot` connect `ValueError` to `RepositorySnapshot`, `SnapshotToolRegistry`, `ValueError`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `SnapshotToolRegistry` connect `SnapshotToolRegistry` to `RepositorySnapshot`, `Run`, `ValueError`, `ValueError`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 90 inferred relationships involving `ValueError` (e.g. with `_collect_check()` and `_load_seed()`) actually correct?**
  _`ValueError` has 90 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `RepositorySnapshot` (e.g. with `EvaluationResult` and `ContainerRunner`) actually correct?**
  _`RepositorySnapshot` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 56 inferred relationships involving `AgentRole` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`AgentRole` has 56 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `RunSource` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`RunSource` has 38 INFERRED edges - model-reasoned connections that need verification._