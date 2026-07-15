from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class EvaluationCase(BaseModel):
    case_id: str
    role: str
    repository_id: int
    pinned_sha: str = Field(min_length=40, max_length=64)
    task_input: str
    source_provenance: str
    expected_evidence: list[str]
    deterministic_assertions: list[str]
    human_rubric: str
    split: str
    label_change_log: list[dict[str, str]] = Field(default_factory=list)

    @field_validator("split")
    @classmethod
    def approved_split(cls, value: str) -> str:
        if value not in {"development", "held_out"}:
            raise ValueError("split must be development or held_out")
        return value

    def agent_input(self) -> dict[str, object]:
        """Deliberately excludes labels, expected evidence, and scoring assertions."""
        return {
            "case_id": self.case_id,
            "repository_id": self.repository_id,
            "pinned_sha": self.pinned_sha,
            "task_input": self.task_input,
        }
