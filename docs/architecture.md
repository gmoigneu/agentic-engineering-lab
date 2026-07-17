# System architecture

## Design principles

- The model proposes. Deterministic code authorizes and executes.
- A run is a durable state machine, not a background function call.
- Target-repository content is evidence and may be adversarial.
- Credentials remain in the control plane.
- Output is structured data first and readable prose second.
- Evaluation is a product feature, not a reporting afterthought.

## Components

| Component | Responsibility | Trust level |
| --- | --- | --- |
| API service | Webhook verification, manual intake, replay, run inspection, policy commands | Trusted |
| PostgreSQL | Source of truth for events, runs, leases, artifacts, policies, metrics, and reviews | Trusted |
| Worker | Leases jobs, orchestrates explicit states, invokes model gateway, writes artifacts | Trusted |
| Capability gateway | Mints scoped GitHub tokens, fetches snapshots, reads GitHub data, applies approved patch | Trusted and policy-bearing |
| Model gateway | OpenRouter request construction, provider policy, usage capture, Langfuse correlation | Trusted but external-network facing |
| Executor launcher | Creates disposable Docker executor from a pinned image and snapshot | Trusted and policy-bearing |
| Executor | Runs named recipes and produces patch plus artifacts with no credentials or default egress | Untrusted execution boundary |
| Langfuse | Private trace and prompt observability | External supplemental system |
| GitHub | Event source and target-repository API | External system |

## Local topology

Docker Compose starts `api`, `worker`, `postgres`, and `executor-launcher`. Executors are short-lived child containers started by the launcher. The API and worker never expose an unauthenticated public control endpoint. Local development uses signed fixtures. A Cloudflare Tunnel is created only for a selected live webhook demonstration.

The executor image is built before a run. It contains the approved runtime and fixed argv recipe adapters. It receives a read-only `/work/source` mount, a read-only typed request under `/work/input`, an ephemeral writable `/work/workspace`, a writable `/work/output`, and no injected environment secret. It cannot call the GitHub API or OpenRouter. The trusted launcher may access the Docker socket. The child executor never receives that socket.

## Control flow

1. The API verifies an event or validates a manual request.
2. The API stores the immutable event record and a queued run atomically.
3. The worker leases the run and loads lab-owned policy and manifest versions.
4. The capability gateway fetches only the needed GitHub data or source snapshot at the pinned SHA.
5. The worker invokes a single bounded Pydantic AI loop through the model gateway.
6. Typed tools validate each request before the gateway or executor performs work.
7. The worker stores structured output, citations, policy decisions, usage, timing, and terminal state.
8. A CI run that reaches `ready_to_push` asks the capability gateway to recheck the head SHA and apply the patch. The gateway is the sole writer to GitHub.

## Module layout

```text
src/agentic_lab/
  api/                 FastAPI routes, webhook verification, inspector views
  config/              settings and dependency wiring
  db/                  models, repositories, migrations helpers
  domain/              Pydantic artifacts, enums, state transitions
  runs/                intake, leasing, orchestration, budgets, terminal handling
  agents/              scout, assessor, ci diagnosis prompts and loop adapters
  tools/               typed read tools and result serializers
  gateway/             GitHub, OpenRouter, capability, tracing, redaction adapters
  executor/            snapshot, recipe, container, patch and artifact handling
  policy/              allowlists, patch checks, protected paths, push gate
  evaluation/          fixtures, evaluators, reporting, human review
  web/                 server-rendered inspector templates and view models
tests/
  unit/ integration/ contract/ fixtures/
```

## Dependency direction

Routes depend on application services. Application services depend on domain interfaces. Gateway and database adapters implement those interfaces. Agent code may depend on typed tools and domain models but cannot import gateway credentials, database sessions, or executor-launching code directly. Policy code is pure where practical and must be callable in unit tests without Docker, GitHub, OpenRouter, or Langfuse.

## Configuration

Use Pydantic Settings with one environment namespace. Required secrets include GitHub App ID, GitHub private key, webhook secret, OpenRouter key, and Langfuse keys. Non-secret settings include allowlisted repository IDs, Postgres URL, Docker image digest, default budgets, and trace environment. Validate configuration at startup. Never print secret values or full settings objects.

## Failure handling

Workers use leased jobs. A lease has an owner, expiry, heartbeat, attempt number, and reason. A crashed worker leaves a lease that another worker can reclaim after expiry. Retries apply only to transient control-plane failures and are bounded. Invalid model output, policy rejection, unavailable evidence, and budget exhaustion are terminal evidence-bearing outcomes, not infrastructure retries.
