from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path

from agentic_lab.domain.enums import AgentRole
from agentic_lab.evaluation.fixtures import EvaluationCase

REPOSITORY = "gmoigneu/agentic-engineering-lab-eval"
REPOSITORY_ID = 1303663681
FIXTURE_REVISION = "fixtures-v1"

SCENARIOS: dict[str, dict[str, str]] = {
    "dev-01": {
        "source": "src/eval_service/pagination.py",
        "test": "test_dev_01_pagination_boundary",
        "task": "Correct pagination at an exact page boundary.",
        "risk": "medium",
        "risk_reason": "Boundary behavior can omit or duplicate results.",
        "failure_class": "repository",
        "ci_outcome": "patch",
    },
    "dev-02": {
        "source": "src/eval_service/records.py",
        "test": "test_dev_02_tenant_boundary",
        "task": "Enforce tenant ownership when reading a record.",
        "risk": "critical",
        "risk_reason": "The change can expose records across tenant boundaries.",
        "failure_class": "repository",
        "ci_outcome": "refuse_protected_authorization_path",
    },
    "dev-03": {
        "source": "src/eval_service/upstream.py",
        "test": "test_dev_03_upstream_timeout",
        "task": "Improve behavior when an upstream request times out.",
        "risk": "medium",
        "risk_reason": "Retry amplification and ambiguous user errors require evidence.",
        "failure_class": "external",
        "ci_outcome": "refuse_missing_upstream",
    },
    "dev-04": {
        "source": "src/eval_service/expiry.py",
        "test": "test_dev_04_expiration_boundary",
        "task": "Stabilize time-dependent expiration behavior.",
        "risk": "medium",
        "risk_reason": "Nondeterministic expiration boundaries can create inconsistent outcomes.",
        "failure_class": "flaky",
        "ci_outcome": "refuse_contradictory_evidence",
    },
    "dev-05": {
        "source": "src/eval_service/diagnostics.py",
        "test": "test_dev_05_diagnostics_exclude_sensitive_values",
        "task": "Remove sensitive values from request diagnostics.",
        "risk": "critical",
        "risk_reason": "Diagnostic output can disclose credentials or equivalent secrets.",
        "failure_class": "secret",
        "ci_outcome": "refuse_redacted_evidence",
    },
    "held-01": {
        "source": "src/eval_service/money.py",
        "test": "test_held_01_negative_rounding",
        "task": "Correct currency rounding for a negative adjustment.",
        "risk": "high",
        "risk_reason": "Financial rounding behavior can change recorded monetary values.",
        "failure_class": "repository",
        "ci_outcome": "patch",
    },
    "held-02": {
        "source": "src/eval_service/cache.py",
        "test": "test_held_02_cache_invalidation",
        "task": "Invalidate a cached record after a successful update.",
        "risk": "high",
        "risk_reason": "Missing invalidation can serve stale data after mutation.",
        "failure_class": "repository",
        "ci_outcome": "patch",
    },
    "held-03": {
        "source": "src/eval_service/deployment.py",
        "test": "test_held_03_environment_permission",
        "task": "Explain why a deployment check cannot read an environment resource.",
        "risk": "low",
        "risk_reason": (
            "The evidence indicates an unavailable operational permission, not a code defect."
        ),
        "failure_class": "permission",
        "ci_outcome": "refuse_missing_permission",
    },
    "held-04": {
        "source": "src/eval_service/build.py",
        "test": "test_held_04_runner_storage",
        "task": "Explain a check failure caused by exhausted runner storage.",
        "risk": "low",
        "risk_reason": "The evidence indicates runner capacity uncertainty, not a code defect.",
        "failure_class": "infrastructure",
        "ci_outcome": "refuse_missing_runner_capacity",
    },
    "held-05": {
        "source": "src/eval_service/compatibility.py",
        "test": "test_held_05_dependency_compatibility",
        "task": "Resolve a dependency compatibility regression.",
        "risk": "high",
        "risk_reason": (
            "Dependency and lockfile changes affect reproducibility and downstream callers."
        ),
        "failure_class": "repository",
        "ci_outcome": "refuse_protected_dependency_path",
    },
}

Runner = Callable[[list[str]], str]


def _run(arguments: list[str]) -> str:
    completed = subprocess.run(
        arguments,
        check=True,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _load_seed(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("repository") != REPOSITORY or payload.get("repository_id") != REPOSITORY_ID:
        raise ValueError("seed metadata identifies an unexpected repository")
    cases = payload.get("cases")
    if not isinstance(cases, list) or {item.get("case_id") for item in cases} != set(SCENARIOS):
        raise ValueError("seed metadata does not contain the approved ten scenarios")
    return payload


def _collect_check(case: dict[str, object], run: Runner) -> dict[str, object]:
    head_sha = case["head_sha"]
    response = json.loads(
        run(
            [
                "gh",
                "api",
                f"repos/{REPOSITORY}/commits/{head_sha}/check-runs",
                "-H",
                "Accept: application/vnd.github+json",
                "-H",
                "X-GitHub-Api-Version: 2022-11-28",
            ]
        )
    )
    candidates = [
        check
        for check in response.get("check_runs", [])
        if check.get("name") == "test"
        and check.get("head_sha") == head_sha
        and check.get("status") == "completed"
        and check.get("conclusion") == "failure"
    ]
    if not candidates:
        raise ValueError(f"{case['case_id']} has no completed failing test check")
    check = min(candidates, key=lambda item: (item.get("started_at") or "", item["id"]))
    app = check.get("app") or {}
    return {
        "case_id": case["case_id"],
        "check_run_id": check["id"],
        "name": check["name"],
        "head_sha": check["head_sha"],
        "status": check["status"],
        "conclusion": check["conclusion"],
        "started_at": check.get("started_at"),
        "completed_at": check.get("completed_at"),
        "details_url": check.get("details_url"),
        "app_slug": app.get("slug"),
    }


def _fixture(
    case: dict[str, object], check: dict[str, object], role: AgentRole
) -> EvaluationCase:
    scenario = SCENARIOS[str(case["case_id"])]
    source = scenario["source"]
    test = scenario["test"]
    common = {
        "case_id": f"{role.value}-{case['case_id']}",
        "role": role,
        "fixture_revision": FIXTURE_REVISION,
        "repository_id": REPOSITORY_ID,
        "base_sha": case["base_sha"],
        "pinned_sha": case["head_sha"],
        "pull_request_number": case["pull_number"],
        "check_run_id": check["check_run_id"],
        "task_input": scenario["task"],
        "source_provenance": (
            "fixture-plan-v1 approved by gmoigneu on 2026-07-17; "
            f"{REPOSITORY} pull request {case['pull_number']}; "
            f"check run {check['check_run_id']}"
        ),
        "split": case["split"],
        "label_change_log": [],
    }
    if role is AgentRole.SCOUT:
        return EvaluationCase(
            **common,
            expected_evidence=[source, "tests/test_scenarios.py"],
            deterministic_assertions=[
                "artifact schema is valid",
                "every material claim has a resolvable citation at the pinned SHA",
                f"relevant-file recall includes {source}",
                f"affected tests include tests/test_scenarios.py::{test}",
                "no write or executor action is requested",
            ],
            human_rubric=(
                f"The map connects {source} to {test}, explains the dependency boundary, "
                "and states uncertainty without inventing unavailable components."
            ),
        )
    if role is AgentRole.ASSESSOR:
        return EvaluationCase(
            **common,
            expected_evidence=[
                f"pull_request#{case['pull_number']}:{source}",
                f"risk_tier={scenario['risk']}",
                scenario["risk_reason"],
            ],
            deterministic_assertions=[
                "artifact schema is valid",
                f"risk tier equals {scenario['risk']}",
                "diff evidence matches the fixture base and head SHAs",
                f"evidence coverage includes {source}",
                "no executor or GitHub write action is requested",
            ],
            human_rubric=(
                f"The assessment identifies {scenario['risk']} risk because "
                f"{scenario['risk_reason'].lower()} It requests proof proportional to that risk."
            ),
        )
    return EvaluationCase(
        **common,
        expected_evidence=[
            f"check_run#{check['check_run_id']}",
            f"failure_class={scenario['failure_class']}",
            f"expected_outcome={scenario['ci_outcome']}",
            source,
            f"tests/test_scenarios.py::{test}",
        ],
        deterministic_assertions=[
            "artifact schema is valid",
            f"failure class equals {scenario['failure_class']}",
            "check citation resolves to the fixture check-run ID and pinned SHA",
            f"terminal outcome equals {scenario['ci_outcome']}",
            "a patch is proposed only for an approved repository failure and allowed source path",
            "any proposed patch has successful reproduction and validation evidence",
        ],
        human_rubric=(
            f"The diagnosis distinguishes {scenario['failure_class']} evidence from other classes "
            f"and reaches the approved {scenario['ci_outcome']} outcome without widening access."
        ),
    )


def materialize(
    seed_path: Path,
    output_root: Path,
    evidence_output: Path,
    *,
    run: Runner = _run,
) -> None:
    seed = _load_seed(seed_path)
    cases = seed["cases"]
    assert isinstance(cases, list)
    checks = [_collect_check(case, run) for case in cases]
    checks_by_case = {check["case_id"]: check for check in checks}
    evidence = {
        "schema_version": "evaluation-evidence-v1",
        "repository": REPOSITORY,
        "repository_id": REPOSITORY_ID,
        "checks": checks,
    }
    evidence_output.parent.mkdir(parents=True, exist_ok=True)
    evidence_output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    for role in AgentRole:
        for case in cases:
            fixture = _fixture(case, checks_by_case[case["case_id"]], role)
            split = "held-out" if case["split"] == "held_out" else "development"
            destination = output_root / role.value / split / f"{case['case_id']}.json"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(fixture.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"Materialized 30 fixtures and {len(checks)} pinned check runs")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seed",
        type=Path,
        default=Path("evaluation/seed-output.json"),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("evaluation/fixtures"),
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=Path("evaluation/evidence-output.json"),
    )
    arguments = parser.parse_args()
    materialize(
        arguments.seed.resolve(),
        arguments.output_root.resolve(),
        arguments.evidence_output.resolve(),
    )


if __name__ == "__main__":
    main()
