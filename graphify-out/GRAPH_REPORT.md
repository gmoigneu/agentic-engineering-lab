# Graph Report - agentic-engineering-lab  (2026-07-17)

## Corpus Check
- 106 files · ~37,630 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 697 nodes · 1665 edges · 57 communities (45 shown, 12 thin omitted)
- Extraction: 58% EXTRACTED · 42% INFERRED · 0% AMBIGUOUS · INFERRED: 691 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `90b9831c`
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
- RunLease
- What You Must Do When Invoked
- _process_github_delivery
- Settings
- PolicyOutcome
- Product requirements document
- Implementation plan
- graphify reference: extra exports and benchmark
- System architecture
- API, webhook, and tool contracts
- Evaluation specification
- Security and policy specification
- _app
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
- FastAPI
- extraction-spec.md
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- __init__.py
- agentic-engineering-lab

## God Nodes (most connected - your core abstractions)
1. `AgentRole` - 57 edges
2. `RunSource` - 44 edges
3. `RunStatus` - 44 edges
4. `RepositorySnapshot` - 44 edges
5. `SnapshotToolRegistry` - 40 edges
6. `Run` - 34 edges
7. `RunCreate` - 29 edges
8. `ModelBudget` - 27 edges
9. `transition_run()` - 27 edges
10. `Output` - 26 edges

## Surprising Connections (you probably didn't know these)
- `test_assessor_requires_evidence_coverage()` --calls--> `run_assessor()`  [INFERRED]
  tests/unit/test_assessor.py → src/agentic_lab/agents/assessor.py
- `_app()` --calls--> `create_app()`  [INFERRED]
  tests/integration/test_intake_and_leases.py → src/agentic_lab/api/app.py
- `test_failed_check_routes_to_ci()` --calls--> `_queue_check_run()`  [INFERRED]
  tests/unit/test_webhook_routing.py → src/agentic_lab/api/app.py
- `_app()` --calls--> `Settings`  [INFERRED]
  tests/integration/test_intake_and_leases.py → src/agentic_lab/config/settings.py
- `test_invalid_signature_records_safe_metadata_without_a_run()` --indirect_call--> `WebhookEvent`  [INFERRED]
  tests/integration/test_intake_and_leases.py → src/agentic_lab/db/models.py

## Import Cycles
- None detected.

## Communities (57 total, 12 thin omitted)

### Community 0 - "RepositorySnapshot"
Cohesion: 0.05
Nodes (39): CapabilityAuditPort, GitHubReadPort, Protocol, Archive, GitHubAppArchiveReader, PinnedArchiveReader, Client, Small adapter seam for the GitHub App archive client. (+31 more)

### Community 1 - "Run"
Cohesion: 0.10
Nodes (51): LookupError, Run, RunCausalLink, RunTransition, RunCreate, CapabilityGateway, Role-gated facade. It deliberately has no generic REST method or write method., ModelGateway (+43 more)

### Community 2 - "SnapshotToolRegistry"
Cohesion: 0.09
Nodes (45): ModelHTTPError, OpenAIChatModel, UUID, run_assessor(), classify_failure(), UUID, Conservative classification. Ambiguous logs never enable patching., run_ci_diagnosis() (+37 more)

### Community 3 - "AgentRole"
Cohesion: 0.11
Nodes (48): build_refusal(), requires_refusal(), UUID, run_scout(), AgentRole, RunSource, RunStatus, ArtifactBase (+40 more)

### Community 4 - "push_validated_patch"
Cohesion: 0.10
Nodes (31): apply_validated_patch(), GitHubBranchWriter, Protocol, Narrow port implemented only by the trusted GitHub App adapter., Sole write path. It rechecks the head SHA after policy evaluation., ValidatedPatchRequest, Session, record_decision() (+23 more)

### Community 5 - "ValueError"
Cohesion: 0.09
Nodes (22): ContainerRunner, ExecutorSpec, launch_recipe(), Protocol, _contains_command_key(), ExecutionManifest, ManifestBudgets, Any (+14 more)

### Community 6 - "EvaluationCase"
Cohesion: 0.12
Nodes (27): BatchConfiguration, CaseResult, _cost_per_success(), export_scorecard(), _failure_rate(), held_out_complete(), load_cases(), load_role_dataset() (+19 more)

### Community 7 - "TraceExporter"
Cohesion: 0.10
Nodes (19): AsyncClient, ModelCallMetadata, LangfuseClient, LangfuseTraceSink, Any, Protocol, Match Langfuse's deterministic W3C trace-ID derivation., trace_id_for_run() (+11 more)

### Community 8 - "RunLease"
Cohesion: 0.12
Nodes (18): RunLease, LeaseHeartbeat, LeaseLostError, Any, RuntimeError, Renew one durable lease while its worker attempt is active., claim_next_run(), heartbeat_lease() (+10 more)

### Community 9 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 10 - "_process_github_delivery"
Cohesion: 0.18
Nodes (17): _detail(), _effective_budget(), _process_github_delivery(), Session, _queue_check_run(), _queue_webhook_run(), _record_invalid_delivery(), _record_safe_rejection() (+9 more)

### Community 11 - "Settings"
Cohesion: 0.13
Nodes (10): BaseSettings, create_app(), sessionmaker, get_settings(), Process configuration. Secrets are intentionally never serialized or logged., Settings, TestClient, test_manual_run_requires_operator_and_allowlisted_repository() (+2 more)

### Community 12 - "PolicyOutcome"
Cohesion: 0.26
Nodes (15): DeclarativeBase, Base, Artifact, CitationRecord, Evaluation, HumanReview, ModelCall, PolicyDecision (+7 more)

### Community 13 - "Product requirements document"
Cohesion: 0.15
Nodes (13): CI fixer, Functional requirements, Goals, Non-goals for v1, Observability and review, Product acceptance, Product requirements document, Product statement (+5 more)

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
Cohesion: 0.25
Nodes (7): API, webhook, and tool contracts, Capability gateway, CI push gate, GitHub webhook intake, HTTP API, Model gateway, Tool contracts

### Community 18 - "Evaluation specification"
Cohesion: 0.25
Nodes (7): Case design, Dataset structure, Evaluation specification, Evaluators, Metrics, Model comparison protocol, Reporting

### Community 19 - "Security and policy specification"
Cohesion: 0.25
Nodes (7): Audit and incident response, Authoritative inputs, Credential policy, Patch policy, Redaction policy, Security and policy specification, Trust boundaries

### Community 20 - "_app"
Cohesion: 0.52
Nodes (6): _app(), sessionmaker, _signature(), test_invalid_signature_records_safe_metadata_without_a_run(), test_signed_fixture_replay_uses_the_intake_path(), test_valid_signed_delivery_creates_one_queued_run_and_deduplicates()

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
Cohesion: 0.40
Nodes (4): Session, store_evaluation(), Path, test_fixture_and_evaluation_records_require_scoring_inputs()

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
Cohesion: 0.50
Nodes (3): build_session_factory(), Session, sessionmaker

## Knowledge Gaps
- **107 isolated node(s):** `agentic-engineering-lab`, `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)`, `Step 1 - Ensure graphify is installed` (+102 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **12 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentRole` connect `AgentRole` to `RepositorySnapshot`, `Run`, `SnapshotToolRegistry`, `EvaluationCase`, `RunLease`, `_process_github_delivery`, `PolicyOutcome`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Why does `Run` connect `Run` to `AgentRole`, `push_validated_patch`, `RunLease`, `_process_github_delivery`, `PolicyOutcome`, `_app`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Why does `SnapshotToolRegistry` connect `SnapshotToolRegistry` to `RepositorySnapshot`, `Run`, `AgentRole`, `ValueError`, `TraceExporter`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Are the 53 inferred relationships involving `AgentRole` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`AgentRole` has 53 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `ValueError` (e.g. with `run_assessor()` and `build_refusal()`) actually correct?**
  _`ValueError` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `RunSource` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`RunSource` has 38 INFERRED edges - model-reasoned connections that need verification._
- **Are the 39 inferred relationships involving `RunStatus` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`RunStatus` has 39 INFERRED edges - model-reasoned connections that need verification._