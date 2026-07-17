# Graph Report - agentic-engineering-lab  (2026-07-17)

## Corpus Check
- 167 files · ~53,386 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 889 nodes · 2169 edges · 66 communities (55 shown, 11 thin omitted)
- Extraction: 60% EXTRACTED · 40% INFERRED · 0% AMBIGUOUS · INFERRED: 877 edges (avg confidence: 0.68)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `bc5863f1`
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
- AgentRole
- Settings
- PolicyOutcome
- Product requirements document
- Implementation plan
- graphify reference: extra exports and benchmark
- System architecture
- API, webhook, and tool contracts
- Evaluation specification
- Security and policy specification
- ExecutionManifest
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
- ValueError
- ExecutorTransport
- seed
- apply_text_diff
- ContainerRunner
- Runner

## God Nodes (most connected - your core abstractions)
1. `RepositorySnapshot` - 68 edges
2. `AgentRole` - 64 edges
3. `RunSource` - 44 edges
4. `RunStatus` - 44 edges
5. `SnapshotToolRegistry` - 44 edges
6. `Run` - 34 edges
7. `RunCreate` - 29 edges
8. `transition_run()` - 27 edges
9. `Settings` - 26 edges
10. `PolicyOutcome` - 26 edges

## Surprising Connections (you probably didn't know these)
- `test_snapshot_bounds_model_visible_file_and_search_content()` --calls--> `RepositorySnapshot`  [INFERRED]
  tests/unit/test_completion_contracts.py → src/agentic_lab/tools/snapshot.py
- `test_snapshot_locator_hash_matches_the_exact_cited_excerpt()` --calls--> `RepositorySnapshot`  [INFERRED]
  tests/unit/test_completion_contracts.py → src/agentic_lab/tools/snapshot.py
- `_execute()` --calls--> `launch_recipe()`  [INFERRED]
  scripts/probe_evaluation_executor.py → src/agentic_lab/executor/launcher.py
- `_execute()` --calls--> `RecipeRequest`  [INFERRED]
  scripts/probe_evaluation_executor.py → src/agentic_lab/executor/manifest.py
- `probe()` --calls--> `default_docker_runner()`  [INFERRED]
  scripts/probe_evaluation_executor.py → src/agentic_lab/executor/launcher.py

## Import Cycles
- None detected.

## Communities (66 total, 11 thin omitted)

### Community 0 - "RepositorySnapshot"
Cohesion: 0.07
Nodes (34): CapabilityAuditPort, GitHubReadPort, Protocol, GitHubAppInstallationAuth, Client, bounded_untrusted_text(), CheckAnnotationEvidence, CheckEvidence (+26 more)

### Community 1 - "Run"
Cohesion: 0.07
Nodes (60): LookupError, build_refusal(), classify_failure(), UUID, Conservative classification. Ambiguous logs never enable patching., requires_refusal(), run_ci_diagnosis(), _queue_check_run() (+52 more)

### Community 2 - "SnapshotToolRegistry"
Cohesion: 0.08
Nodes (46): ModelHTTPError, OpenAIChatModel, BudgetExhaustedError, _content(), _float_cost(), _message(), _metadata(), ModelBudget (+38 more)

### Community 3 - "AgentRole"
Cohesion: 0.09
Nodes (22): AsyncClient, LangfuseClient, LangfuseTraceSink, Any, Protocol, Match Langfuse's deterministic W3C trace-ID derivation., trace_id_for_run(), TraceExporter (+14 more)

### Community 4 - "push_validated_patch"
Cohesion: 0.07
Nodes (38): main(), Path, render(), apply_validated_patch(), GitHubAppBranchWriter, GitHubBranchWriter, Protocol, Narrow port implemented only by the trusted GitHub App adapter. (+30 more)

### Community 5 - "ValueError"
Cohesion: 0.26
Nodes (13): ExecutorSpec, BaseModel, RecipeExecutionRequest, RecipeExecutionResult, RecipeOutputArtifact, Path, _request(), _result() (+5 more)

### Community 6 - "EvaluationCase"
Cohesion: 0.07
Nodes (40): BatchBudget, BatchConfiguration, CaseResult, _cost_per_success(), export_scorecard(), _failure_rate(), held_out_complete(), load_cases() (+32 more)

### Community 7 - "TraceExporter"
Cohesion: 0.27
Nodes (9): Runner, _collect_check(), _fixture(), _load_seed(), main(), materialize(), Path, Path (+1 more)

### Community 8 - "LeaseHeartbeat"
Cohesion: 0.11
Nodes (15): LeaseHeartbeat, LeaseLostError, Any, RuntimeError, Renew one durable lease while its worker attempt is active., heartbeat_lease(), _new_lease(), datetime (+7 more)

### Community 9 - "What You Must Do When Invoked"
Cohesion: 0.08
Nodes (24): For /graphify add and --watch, For /graphify query, For the commit hook and native CLAUDE.md integration, For --update and --cluster-only, /graphify, Honesty Rules, Interpreter guard for subcommands, Part A - Structural extraction for code files (+16 more)

### Community 10 - "AgentRole"
Cohesion: 0.09
Nodes (64): DeclarativeBase, create_app(), _detail(), _effective_budget(), _process_github_delivery(), FastAPI, Session, sessionmaker (+56 more)

### Community 11 - "Settings"
Cohesion: 0.09
Nodes (18): BaseSettings, get_settings(), Process configuration. Secrets are intentionally never serialized or logged., Settings, create_app(), FastAPI, TestClient, test_manual_run_requires_operator_and_allowlisted_repository() (+10 more)

### Community 12 - "PolicyOutcome"
Cohesion: 0.14
Nodes (26): UUID, run_assessor(), UUID, run_scout(), Citation, Claim, ScoutArtifact, citation_coverage() (+18 more)

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

### Community 20 - "ExecutionManifest"
Cohesion: 0.12
Nodes (18): launch_recipe(), _contains_command_key(), ExecutionManifest, ManifestBudgets, Any, BaseModel, RecipeRequest, _validate_arguments() (+10 more)

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
Cohesion: 0.22
Nodes (12): _pydantic_tools(), FileReadResult, HistoryEntry, BaseModel, Search parsed structure without exposing ast-grep or shell command text., An immutable, credential-free source snapshot supplied by the gateway., RepositorySnapshot, SourceLocator (+4 more)

### Community 60 - "ValueError"
Cohesion: 0.13
Nodes (8): _apply_workspace_diff(), execute_request(), main(), Path, _safe_artifact_path(), adapter_argv(), Recipe, ValueError

### Community 61 - "ExecutorTransport"
Cohesion: 0.21
Nodes (8): default_docker_runner(), DockerContainerRunner, Any, Path, ExecutorTransport, PreparedTransport, Path, restricted_executor_environment()

### Community 62 - "seed"
Cohesion: 0.40
Nodes (8): main(), Path, _run(), seed(), _write(), _materialize(), Path, test_seed_base_passes_and_every_scenario_has_one_failing_check()

### Community 63 - "apply_text_diff"
Cohesion: 0.31
Nodes (9): AppliedFile, apply_text_diff(), _header_path(), parse_text_diff(), TextFilePatch, TextHunk, test_text_patch_accepts_removed_line_that_looks_like_a_header(), test_text_patch_applies_exact_context_and_supports_add_delete() (+1 more)

### Community 64 - "ContainerRunner"
Cohesion: 0.36
Nodes (9): _execute(), main(), probe(), Path, _run(), _snapshot_at(), SnapshotLoader, ContainerRunner (+1 more)

### Community 65 - "Runner"
Cohesion: 0.50
Nodes (3): Path, Runner, test_probe_requires_expected_reproduction_patch_and_lint_outcomes()

## Knowledge Gaps
- **116 isolated node(s):** `agentic-engineering-lab`, `Usage`, `What graphify is for`, `Step 0 - GitHub repos and multi-path merge (only if a URL or several paths)`, `Step 1 - Ensure graphify is installed` (+111 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **11 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `AgentRole` connect `AgentRole` to `RepositorySnapshot`, `Run`, `SnapshotToolRegistry`, `EvaluationCase`, `TraceExporter`, `PolicyOutcome`?**
  _High betweenness centrality (0.089) - this node is a cross-community bridge._
- **Why does `RepositorySnapshot` connect `ValueError` to `ContainerRunner`, `RepositorySnapshot`, `Run`, `SnapshotToolRegistry`, `Runner`, `ValueError`, `PolicyOutcome`, `ExecutionManifest`, `ExecutorTransport`?**
  _High betweenness centrality (0.084) - this node is a cross-community bridge._
- **Why does `SnapshotToolRegistry` connect `SnapshotToolRegistry` to `RepositorySnapshot`, `Run`, `AgentRole`, `PolicyOutcome`, `ValueError`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 91 inferred relationships involving `ValueError` (e.g. with `_collect_check()` and `_load_seed()`) actually correct?**
  _`ValueError` has 91 INFERRED edges - model-reasoned connections that need verification._
- **Are the 47 inferred relationships involving `RepositorySnapshot` (e.g. with `EvaluationResult` and `ContainerRunner`) actually correct?**
  _`RepositorySnapshot` has 47 INFERRED edges - model-reasoned connections that need verification._
- **Are the 56 inferred relationships involving `AgentRole` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`AgentRole` has 56 INFERRED edges - model-reasoned connections that need verification._
- **Are the 38 inferred relationships involving `RunSource` (e.g. with `Artifact` and `CitationRecord`) actually correct?**
  _`RunSource` has 38 INFERRED edges - model-reasoned connections that need verification._