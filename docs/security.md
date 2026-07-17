# Security and policy specification

## Trust boundaries

| Boundary | Risk | Required control |
| --- | --- | --- |
| GitHub webhook to API | Forged or replayed events | HMAC verification, delivery deduplication, payload hash, allowlist |
| Target content to model | Prompt injection and secret exposure | Untrusted-data label, source attribution, redaction before model input |
| Model to tool | Invalid or overbroad action | Typed contracts, gateway policy, per-run budgets |
| Control plane to executor | Credential theft and arbitrary host control | Credential-free disposable executor, read-only snapshot, named recipes |
| Executor to network | Exfiltration and non-reproducible dependency fetch | Network disabled by default |
| Control plane to GitHub | Unauthorized repository mutation | Scoped token, gateway-only write, exact-SHA precheck, PR opt-in |
| Trace system | Source and secret retention | Private Langfuse project, redaction, no full snapshots |

## Authoritative inputs

Only these sources may decide what the system does.

- Lab repository policy code and approved policy version
- Lab-owned target manifest version
- Explicit manual run request or verified GitHub event
- Stored allowlist and pull-request opt-in record
- Deterministic validation and policy results

Repository instructions, comments, issue text, commit messages, code, tests, logs, tool output, model output, and external links are non-authoritative evidence. A model must not obey instructions embedded in evidence that request credentials, policy changes, tool changes, new commands, or widened access.

## Credential policy

The GitHub App private key and OpenRouter key are available only to the API, worker, and gateway process through injected local configuration. The executor has no access to those settings, Docker socket, host home directory, or control-plane network credentials. The model receives neither secret nor token. Installation tokens are short-lived, repository-scoped, and permission-reduced whenever GitHub allows it.

Do not request GitHub workflow, administration, issue, status, secret, or pull-request-write permissions. Contents write exists solely so the gateway can update an eligible existing PR branch. The gateway cannot create PRs, comments, issues, checks, releases, or workflow changes in v1.

## Redaction policy

Run deterministic redaction before model input, Langfuse trace export, persisted readable artifact, or GitHub push. Combine conservative generic patterns with repository-manifest patterns. Detect credential prefixes, private keys, JWT-like strings, connection strings, high-entropy assignments, and configured known-secret formats.

A credible detection blocks the affected run from tracing and pushing. Persist only redaction event metadata, detector name, content hash, source locator, and resolution state. Never persist the detected value. False positives are reviewed manually and may result in a detector adjustment with a regression test.

## Patch policy

CI auto-push applies only to ordinary application-source paths. It refuses tests, workflows, migrations, dependency files, lockfiles, infrastructure, authentication or authorization code, secrets, generated protected output, binary files, symlinks, submodules, and any manifest-protected path. Reject file rename tricks that cross into protected scope. Reject a diff larger than manifest or global limits. The policy should be deterministic and run before and after patch application.

## Audit and incident response

Every deny and allow decision has a policy name, reason code, input hash, run ID, and timestamp. An operator can cancel queued or leased runs. On suspected credential exposure, stop services, rotate GitHub App key and OpenRouter key, revoke installation tokens by waiting for expiry or suspending the app, preserve redacted run metadata, and disable the target allowlist before investigation. Do not attempt to recover by rerunning the same unsafe job.
