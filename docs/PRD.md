# Product requirements document

## Product statement

Agentic Engineering Lab is a local-first control plane that runs bounded coding-agent workflows against approved GitHub repositories. It makes the operational evidence behind an agent decision inspectable and measures complete outcomes rather than attractive responses.

The product supports three roles. The repository scout is read-only. The pull-request risk assessor is read-only. The CI fixer can update an opted-in pull-request branch only after reproduction, validation, policy checks, and an exact revision check succeed.

## Users and jobs

| User | Job to be done | Successful result |
| --- | --- | --- |
| Senior developer | Understand a change before implementing it | A sequenced plan grounded in files, symbols, history, tests, and explicit unknowns |
| Reviewer or engineering manager | Focus review effort on meaningful risk | A risk tier with evidence, required proof, missing signals, and suggested expertise |
| Platform engineer | Triage a failed CI run safely | A correct diagnosis, a validated source patch when safe, or an actionable refusal |
| Series producer | Explain how agents earn autonomy | Reproducible artifacts, measurements, failures, costs, latency, and review effort |

## Goals

- Run every workflow against a pinned repository revision and an explicit policy profile.
- Produce typed, citation-backed output that can be evaluated without interpreting prose alone.
- Make model, provider, prompt, tool, policy, and evaluator configuration reproducible per run.
- Separate model judgment from deterministic enforcement.
- Support local Docker Compose operation and signed GitHub webhook replay.
- Compare three pinned model candidates on the same scout tasks.
- Preserve failures, refusals, invalid outputs, and blocked actions as first-class results.

## Non-goals for v1

- Autonomous merges, default-branch updates, workflow edits, test edits, migrations, dependency updates, infrastructure changes, or changes to protected paths.
- Any target repository other than the initial Mission Control allowlist.
- Cloud deployment, multi-user tenancy, a hosted dashboard, notification delivery, or background scale-out.
- General shell access, subagent delegation, semantic repository indexes, language servers, MCP, LangChain, LangGraph, Redis, or a separate frontend.
- A universal model benchmark or a claim that results generalize outside the labeled task set.

## Functional requirements

### Run intake

- PRD-001. The control plane shall create a run from a manual request, a replay fixture, or an accepted GitHub webhook.
- PRD-002. Webhook processing shall verify the GitHub signature before parsing the payload.
- PRD-003. Event intake shall persist the delivery ID and queued run in one transaction.
- PRD-004. Duplicate delivery IDs shall return success without creating a second run.
- PRD-005. A run shall pin target repository, event source, commit SHA, manifest version, policy version, and agent role before model execution.

### Scout

- PRD-010. The scout shall use only read tools over the pinned snapshot.
- PRD-011. The scout shall output relevant files and symbols, dependency and blast-radius analysis, affected tests, a sequenced implementation plan, risks, unknowns, confidence, and evidence citations.
- PRD-012. The scout shall not receive a GitHub token, write tool, or arbitrary command tool.

### Risk assessor

- PRD-020. The assessor shall consume a validated scout map, a pull-request diff, and permitted history signals.
- PRD-021. The assessor shall output risk tier, confidence, evidence, likely failure modes, required tests or rollout controls, suggested reviewer expertise, and unavailable signals.
- PRD-022. A risk tier without evidence coverage shall be invalid output.

### CI fixer

- PRD-030. A completed failing check run shall create a CI diagnosis run only for the initial allowlisted target repository.
- PRD-031. The fixer shall classify the failure before requesting a patch.
- PRD-032. The executor shall receive a credential-free pinned source snapshot and may run only named manifest recipes.
- PRD-033. The fixer may make one automatic patch attempt for a human-authored pull-request head SHA.
- PRD-034. A push requires an opted-in pull-request allowlist entry, same-repository head branch, unchanged head SHA, successful reproduction, passed relevant validation, allowed source-only patch, and successful deterministic policy checks.
- PRD-035. A refusal shall include failure class, evidence, missing precondition, and next action.

### Observability and review

- PRD-040. Every state transition, model call, tool request, tool result summary, policy decision, cost, and stage duration shall be tied to a run ID.
- PRD-041. Langfuse traces shall use the run ID as their correlation key and remain private.
- PRD-042. The run inspector shall display status timeline, structured artifact, evidence links, patch diff, validation summary, and Langfuse trace link.
- PRD-043. Every held-out result shall support recording human outcome, review minutes, missing evidence, and accept-edit-reject disposition.

## Success measures

| Measure | Definition | Initial use |
| --- | --- | --- |
| Successful task completion | Result passes the task-specific acceptance criteria | Primary quality outcome |
| Unsupported claim rate | Material claims lacking valid evidence divided by material claims | Grounding control |
| Correct refusal rate | Unsafe or unavailable cases refused correctly divided by such cases | Safety outcome |
| Cost per successful task | OpenRouter billed cost divided by successful tasks | Model selection |
| End-to-end latency | Event receipt to terminal outcome | Operational measurement |
| Human review minutes | Manually logged review time per run | Hidden-work measurement |
| Permission violations | Blocked or executed actions outside policy | Zero-tolerance safety measure |
| Regressions introduced | Validated patches later shown to regress behavior | CI fixer safety measure |

## Product acceptance

The product is ready for the series when the Scout vertical slice completes one manually submitted case end to end, all data is visible in the inspector and trace system, deterministic evaluation can score it, and the implementation can prove that the scout had no write capability. CI writing is not ready until every Milestone 8 gate passes.
