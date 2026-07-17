from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agentic_lab.domain.enums import AgentRole
from agentic_lab.evaluation.fixtures import EvaluationCase


class ProviderPolicy(BaseModel):
    provider_allowlist: tuple[str, ...] = Field(min_length=1)
    data_collection: Literal["deny"] = "deny"
    allow_fallbacks: Literal[False] = False


class BatchBudget(BaseModel):
    max_turns: int = Field(default=12, ge=1, le=100)
    max_tool_calls: int = Field(default=40, ge=1, le=1_000)
    max_usd: float = Field(default=3.0, gt=0, le=10)
    max_wall_seconds: int = Field(default=1_200, ge=1, le=86_400)


class BatchConfiguration(BaseModel):
    batch_id: str = Field(min_length=1)
    role: AgentRole
    split: Literal["development", "held_out"]
    model_id: str = Field(min_length=1)
    provider_policy: ProviderPolicy
    budget: BatchBudget = Field(default_factory=BatchBudget)
    prompt_hash: str = Field(min_length=64, max_length=64)
    tool_definitions_hash: str = Field(min_length=64, max_length=64)
    manifest_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    evaluator_version: str = Field(min_length=1)
    fixture_revision: str = Field(min_length=1)
    label_version: str = Field(min_length=1)
    repository_scope: tuple[int, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)

    @field_validator("model_id")
    @classmethod
    def pinned_model(cls, value: str) -> str:
        if value.lower().endswith("latest"):
            raise ValueError("latest aliases are not valid evaluation candidates")
        return value

    @field_validator("prompt_hash", "tool_definitions_hash")
    @classmethod
    def lowercase_hash(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("configuration hashes must be lowercase hexadecimal")
        return value


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    split: str
    passed: bool
    terminal_status: str
    scores: dict[str, bool]
    run_id: str | None = None
    provider: str | None = None
    billed_cost: float | None = None
    latency_ms: int | None = None
    review_minutes: int | None = None
    failure_category: str | None = None
    excluded_reason: str | None = None
    retries: int = 0


@dataclass(frozen=True)
class RoleDataset:
    development: tuple[EvaluationCase, ...]
    held_out: tuple[EvaluationCase, ...]


def load_cases(directory: Path, split: str) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for path in sorted(directory.glob("*.json")):
        case = EvaluationCase.model_validate_json(path.read_text())
        if case.split != split:
            raise ValueError(f"fixture {path.name} is in the wrong split")
        if any(existing.case_id == case.case_id for existing in cases):
            raise ValueError(f"fixture {path.name} has a duplicate case ID")
        cases.append(case)
    return cases


def load_role_dataset(
    development_directory: Path,
    held_out_directory: Path,
    role: AgentRole,
) -> RoleDataset:
    development = tuple(load_cases(development_directory, "development"))
    held_out = tuple(load_cases(held_out_directory, "held_out"))
    for split_name, cases in (("development", development), ("held_out", held_out)):
        if len(cases) != 5:
            raise ValueError(f"{role.value} {split_name} dataset must contain exactly five cases")
        if any(case.role is not role for case in cases):
            raise ValueError(f"{role.value} {split_name} dataset contains another role")
    identifiers = [case.case_id for case in (*development, *held_out)]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("case IDs must be unique across dataset splits")
    return RoleDataset(development, held_out)


def run_batch(
    cases: list[EvaluationCase], execute: Callable[[EvaluationCase], CaseResult]
) -> list[CaseResult]:
    return [execute(case) for case in cases]


def export_scorecard(
    results: list[CaseResult],
    destination: Path,
    configuration: BatchConfiguration | dict[str, object],
    reviewed_case_ids: set[str] | None = None,
) -> None:
    if not results:
        raise ValueError("cannot export an empty batch")
    config = (
        configuration
        if isinstance(configuration, BatchConfiguration)
        else BatchConfiguration.model_validate(configuration)
    )
    if len(results) != 5:
        raise ValueError("a release scorecard requires exactly five cases")
    if len({item.case_id for item in results}) != len(results):
        raise ValueError("a scorecard cannot contain duplicate case IDs")
    if any(item.split != config.split for item in results):
        raise ValueError("scorecard results do not match the configured split")
    if config.split == "held_out" and not held_out_complete(results, reviewed_case_ids or set()):
        raise ValueError("held-out scorecard requires human review for every case")
    payload = {
        "configuration": config.model_dump(mode="json"),
        "task_count": len(results),
        "terminal_outcomes": {
            status: sum(item.terminal_status == status for item in results)
            for status in {item.terminal_status for item in results}
        },
        "success_rate": sum(item.passed for item in results) / len(results),
        "cost_per_successful_task": _cost_per_success(results),
        "unsupported_claim_rate": _failure_rate(results, "citation_coverage"),
        "failure_categories": {
            category: sum(item.failure_category == category for item in results)
            for category in ("infrastructure", "model", "policy", "evaluator")
        },
        "exclusions": [
            {"case_id": item.case_id, "reason": item.excluded_reason}
            for item in results
            if item.excluded_reason is not None
        ],
        "retry_rate": sum(item.retries for item in results) / len(results),
        "missing_data": sorted(
            {
                field
                for item in results
                for field in ("run_id", "provider", "billed_cost", "latency_ms")
                if getattr(item, field) is None
            }
        ),
        "results": [asdict(item) for item in results],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    destination.with_suffix(".md").write_text(_render_scorecard(payload))


def held_out_complete(results: list[CaseResult], reviewed_case_ids: set[str]) -> bool:
    held_out = [item for item in results if item.split == "held_out"]
    return bool(held_out) and all(item.case_id in reviewed_case_ids for item in held_out)


def validate_comparison(configurations: list[BatchConfiguration]) -> None:
    if len(configurations) != 3:
        raise ValueError("a model comparison requires exactly three candidates")
    if len({configuration.model_id for configuration in configurations}) != 3:
        raise ValueError("comparison candidates must use distinct pinned model IDs")
    if any(
        len(configuration.provider_policy.provider_allowlist) != 1
        for configuration in configurations
    ):
        raise ValueError("each comparison candidate requires exactly one pinned provider")
    baseline = configurations[0].model_dump(exclude={"batch_id", "model_id", "provider_policy"})
    if any(
        configuration.model_dump(exclude={"batch_id", "model_id", "provider_policy"}) != baseline
        for configuration in configurations[1:]
    ):
        raise ValueError("comparison candidates must share task and policy configuration")


def _cost_per_success(results: list[CaseResult]) -> float | None:
    successful = sum(item.passed for item in results)
    known_costs = [item.billed_cost for item in results if item.billed_cost is not None]
    return (
        sum(known_costs) / successful if successful and len(known_costs) == len(results) else None
    )


def _failure_rate(results: list[CaseResult], score: str) -> float | None:
    measured = [item.scores[score] for item in results if score in item.scores]
    return 1 - (sum(measured) / len(measured)) if measured else None


def _render_scorecard(payload: dict[str, object]) -> str:
    configuration = payload["configuration"]
    return (
        "# Evaluation scorecard\n\n"
        f"Task count {payload['task_count']}\n\n"
        f"Success rate {payload['success_rate']:.3f}\n\n"
        f"Configuration `{json.dumps(configuration, sort_keys=True)}`\n\n"
        "Results are specific to this dataset and repository. "
        "They do not identify a global model winner.\n"
    )
