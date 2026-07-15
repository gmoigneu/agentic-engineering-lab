from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar
from uuid import UUID

from pydantic import BaseModel

Output = TypeVar("Output", bound=BaseModel)


@dataclass(frozen=True)
class ModelBudget:
    max_turns: int
    max_tool_calls: int
    max_usd: float


@dataclass(frozen=True)
class ModelRequest:
    run_id: UUID
    role: str
    model_id: str
    system_prompt: str
    task: str
    tool_definitions_hash: str
    budget: ModelBudget
    evaluation: bool = False

    @property
    def prompt_hash(self) -> str:
        return hashlib.sha256(self.system_prompt.encode()).hexdigest()


class ModelGateway(Protocol, Generic[Output]):
    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output: ...


class ScriptedModelGateway(Generic[Output]):
    """Test adapter. Production configuration must use a provider-backed gateway."""

    def __init__(self, output: Output) -> None:
        self.output = output
        self.requests: list[ModelRequest] = []

    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output:
        self.requests.append(request)
        return output_type.model_validate(self.output)


def validate_model_id(model_id: str, allowed_models: frozenset[str]) -> None:
    if model_id not in allowed_models or model_id.endswith(":latest") or model_id == "latest":
        raise ValueError("model must be an explicitly configured pinned model ID")
