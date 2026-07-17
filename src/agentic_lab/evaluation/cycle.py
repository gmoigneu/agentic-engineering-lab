from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator, model_validator

from agentic_lab.evaluation.batch import ProviderPolicy


class EvaluationCandidate(BaseModel):
    model_id: str = Field(min_length=1)
    provider_policy: ProviderPolicy

    @field_validator("model_id")
    @classmethod
    def pinned_model(cls, value: str) -> str:
        if value.lower().endswith("latest"):
            raise ValueError("evaluation candidates cannot use latest aliases")
        return value


class EvaluationBudgetAllocation(BaseModel):
    scout_comparison_usd: float = Field(gt=0)
    assessor_usd: float = Field(gt=0)
    ci_usd: float = Field(gt=0)
    per_run_max_usd: float = Field(gt=0, le=1)

    @property
    def total(self) -> float:
        return self.scout_comparison_usd + self.assessor_usd + self.ci_usd


class EvaluationCyclePlan(BaseModel):
    schema_version: str
    repository_id: int = Field(gt=0)
    repository: str = Field(pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    reviewer: str = Field(min_length=1, max_length=255)
    total_budget_usd: float = Field(gt=0, le=100)
    budget_allocation: EvaluationBudgetAllocation
    candidates: list[EvaluationCandidate] = Field(min_length=3, max_length=3)
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def distinct_candidates(self) -> EvaluationCyclePlan:
        if len({candidate.model_id for candidate in self.candidates}) != 3:
            raise ValueError("evaluation cycle requires three distinct model IDs")
        if any(
            len(candidate.provider_policy.provider_allowlist) != 1 for candidate in self.candidates
        ):
            raise ValueError("each candidate requires one pinned provider")
        if abs(self.budget_allocation.total - self.total_budget_usd) > 0.000_001:
            raise ValueError("evaluation allocations must equal the total budget")
        return self


def load_cycle_plan(path: Path) -> EvaluationCyclePlan:
    return EvaluationCyclePlan.model_validate_json(path.read_text())
