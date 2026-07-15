from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID

import httpx
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


class OpenRouterModelGateway:
    """Provider adapter. The API key exists only in this trusted process."""

    def __init__(self, api_key: str, allowed_models: frozenset[str], client: httpx.Client | None = None) -> None:
        self._api_key = api_key
        self._allowed_models = allowed_models
        self._client = client or httpx.Client(base_url="https://openrouter.ai/api/v1", timeout=60)

    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output:
        validate_model_id(request.model_id, self._allowed_models)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.task},
        ]
        for attempt in range(2):
            response = self._client.post(
                "/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": request.model_id,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "provider": {"allow_fallbacks": not request.evaluation, "data_collection": "deny"},
                    "metadata": {"run_id": str(request.run_id), "role": request.role},
                },
            )
            response.raise_for_status()
            content = _content(response.json())
            try:
                return output_type.model_validate_json(content)
            except ValueError as error:
                if attempt:
                    raise ValueError("model output failed schema repair") from error
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Return only corrected JSON matching this schema error: " + str(error),
                    }
                )
        raise AssertionError("unreachable")


def _content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError("provider response has no assistant content") from error
    if isinstance(content, str):
        return content
    return json.dumps(content)
