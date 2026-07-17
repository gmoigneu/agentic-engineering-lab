from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agentic_lab.domain.enums import AgentRole


class LabelChange(BaseModel):
    reason: str = Field(min_length=1)
    author: str = Field(min_length=1)
    timestamp: datetime
    old_value_hash: str = Field(min_length=64, max_length=64)
    new_value_hash: str = Field(min_length=64, max_length=64)


class EvaluationCase(BaseModel):
    case_id: str
    role: AgentRole
    fixture_revision: str = Field(min_length=1)
    repository_id: int = Field(gt=0)
    base_sha: str = Field(min_length=40, max_length=64)
    pinned_sha: str = Field(min_length=40, max_length=64)
    pull_request_number: int = Field(gt=0)
    check_run_id: int = Field(gt=0)
    task_input: str = Field(min_length=1)
    source_provenance: str = Field(min_length=1)
    expected_evidence: list[str] = Field(min_length=1)
    deterministic_assertions: list[str] = Field(min_length=1)
    human_rubric: str = Field(min_length=1)
    split: Literal["development", "held_out"]
    label_change_log: list[LabelChange] = Field(default_factory=list)

    @field_validator("split")
    @classmethod
    def approved_split(cls, value: str) -> str:
        return value

    @field_validator("base_sha", "pinned_sha")
    @classmethod
    def immutable_sha(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("fixture SHA must be immutable lowercase hexadecimal")
        return value

    def agent_input(self) -> dict[str, object]:
        """Deliberately excludes labels, expected evidence, and scoring assertions."""
        payload: dict[str, object] = {
            "case_id": self.case_id,
            "fixture_revision": self.fixture_revision,
            "repository_id": self.repository_id,
            "pinned_sha": self.pinned_sha,
            "task_input": self.task_input,
        }
        if self.role in {AgentRole.ASSESSOR, AgentRole.CI}:
            payload["pull_request_number"] = self.pull_request_number
        if self.role is AgentRole.CI:
            payload["check_run_id"] = self.check_run_id
        return payload
