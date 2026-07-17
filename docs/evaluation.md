# Evaluation specification

## Dataset structure

Each agent has five development cases and five held-out cases. Store fixtures in version control with a case ID, fixture revision, target repository ID, base and head SHAs, pull-request number, check-run ID, task input, source provenance, expected evidence, deterministic assertions, human rubric, split, and label-change log. Held-out scoring keys must not be mounted into an agent runtime or included in a model prompt. Scout input receives neither pull-request nor check-run identity. Assessor input receives the pull-request number. CI input receives both role-required locators.

Development cases support implementation iteration. Held-out cases support final reporting only. A run records split, fixture revision, evaluator version, prompt hash, manifest version, policy version, model ID, provider, and actual cost.

## Case design

| Role | Case ingredients | Core deterministic checks |
| --- | --- | --- |
| Scout | Change request, pinned repository, labeled relevant files, expected affected tests | Valid schema, citation resolution, no write action, relevant-file recall |
| Assessor | Pull request, scout map, labeled risk tier and evidence set | Valid schema, evidence coverage, unavailable-signal handling, high-risk recall |
| CI fixer | Failed check, known failure class, snapshot, reproduction recipe, expected safe outcome | Correct classification, recipe use, patch policy, validation evidence, refusal behavior |

Write labels before the first run on a case. Changes require reason, author, timestamp, old value hash, and new value hash. Do not alter a held-out label because a model result was inconvenient.

## Evaluators

Deterministic evaluators run first and produce atomic pass or fail questions. Examples include cited path exists at pinned SHA, cited line range resolves, output schema validates, agent never requested a disallowed tool, patch changes only allowed paths, named validation passed, and refusal includes required fields.

Subjective evaluation uses a separate pinned judge only when human assessment cannot be reduced to deterministic checks. The judge prompt is versioned and asks atomic questions. It may not use the candidate run model identity as a positive signal. Calibrate judge output against manually scored cases before using it in a scorecard.

Every held-out result is manually reviewed. Record successful, failed, or correctly refused outcome; review minutes; accepted, edited, or rejected disposition; missing evidence; and free-form notes. Human review is the authority when it conflicts with an uncalibrated judge.

## Metrics

Compute metrics per role, model, provider, prompt version, manifest version, dataset split, and evaluation batch.

- Success rate uses task-specific accepted outcomes.
- Unsupported claim rate uses material claims without valid citations.
- Correct refusal rate uses fixtures where patching or confident conclusion is unsafe.
- Cost per successful task uses OpenRouter billed cost and excludes failed tasks from the denominator.
- End-to-end latency starts when intake receives the event and ends at terminal run state.
- Stage timing includes queue wait, snapshot, each model call, each tool call, executor work, evaluation, and push.
- Retry rate counts model repair, transient infrastructure retry, and worker lease reclaim separately.
- Permission violation count includes every blocked request and every executed action found outside policy. The expected executed count is zero.

## Model comparison protocol

Use the scout first. Compare exactly three pinned candidate classes under the same prompt, tools, manifests, budgets, tasks, evaluator versions, data-collection policy, and fallback policy. Pin exactly one provider for each candidate. Provider identity may differ when a model is unavailable from the other candidates' providers. Treat that difference as a named limitation and attribute every result to the actual provider. Never use latest aliases or automatic fallback. Report actual provider, input and output usage, billed cost, latency, retries, completion rate, unsupported claims, and human review minutes.

Do not choose a global winner. A lower-cost candidate wins a role only when it lowers cost per successful outcome without increasing hidden review work or safety failures. State sample size and single-repository limitations in every public result.

The approved $10 cycle reserves $6 for the thirty-run Scout comparison, $2 for ten assessor runs with the selected Scout candidate, and $2 for ten CI runs with that candidate. Every run has a $0.20 hard ceiling. Stop a tranche before submission when its recorded cumulative cost plus the next run ceiling would exceed its allocation.

## Reporting

An evaluation batch exports immutable JSON plus a human-readable scorecard. Include exclusions, infrastructure failures, missing data, exact task count, label version, model configuration, provider policy, and all terminal outcome counts. Preserve representative failures and refusals alongside successes.
