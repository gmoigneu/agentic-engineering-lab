from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from time import monotonic
from typing import Any, Generic, Protocol, TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError
from pydantic_ai import Agent, PromptedOutput, RunContext, UsageLimitExceeded
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIModelProfile
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.usage import RunUsage, UsageLimits

from agentic_lab.gateway.redaction import redact
from agentic_lab.gateway.tracing import TraceExporter
from agentic_lab.tools.registry import SnapshotToolRegistry

Output = TypeVar("Output", bound=BaseModel)


@dataclass(frozen=True)
class ModelBudget:
    max_turns: int
    max_tool_calls: int
    max_usd: float
    max_wall_seconds: int = 1_200


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
    provider_allowlist: tuple[str, ...] = ()
    tools: SnapshotToolRegistry | None = None

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
        self.last_request: ModelRequest | None = None

    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output:
        self.requests.append(request)
        self.last_request = request
        return output_type.model_validate(self.output)


@dataclass(frozen=True)
class ModelCallMetadata:
    provider: str
    usage: dict[str, Any]
    billed_cost: float
    response_id: str | None = None


class BudgetExhaustedError(RuntimeError):
    pass


class ModelGatewayError(RuntimeError):
    pass


class OpenRouterChatModel(OpenAIChatModel):
    """Preserve OpenRouter billing metadata dropped by the OpenAI schema."""

    def __init__(self, model_name: str, **kwargs: Any) -> None:
        super().__init__(model_name, **kwargs)
        self.recorded_provider_details: list[dict[str, Any]] = []

    def _process_provider_details(self, response: Any) -> dict[str, Any] | None:
        details = dict(super()._process_provider_details(response) or {})
        response_extra = response.model_extra or {}
        usage_extra = response.usage.model_extra if response.usage is not None else {}
        provider = response_extra.get("provider")
        cost = (usage_extra or {}).get("cost", response_extra.get("cost"))
        if isinstance(provider, str) and provider:
            details["provider"] = provider
        if cost is not None:
            details["cost"] = cost
        if details:
            self.recorded_provider_details.append(details.copy())
        return details or None


def validate_model_id(model_id: str, allowed_models: frozenset[str]) -> None:
    if model_id not in allowed_models or model_id.lower().endswith("latest"):
        raise ValueError("model must be an explicitly configured pinned model ID")


class OpenRouterModelGateway:
    """Provider adapter. The API key exists only in this trusted process."""

    def __init__(
        self,
        api_key: str,
        allowed_models: frozenset[str],
        client: httpx.Client | None = None,
        allowed_providers: frozenset[str] = frozenset(),
    ) -> None:
        self._api_key = api_key
        self._allowed_models = allowed_models
        self._client = client or httpx.Client(base_url="https://openrouter.ai/api/v1", timeout=60)
        self._allowed_providers = allowed_providers
        self.last_call: ModelCallMetadata | None = None
        self.last_request: ModelRequest | None = None
        self.last_provider_allowlist: tuple[str, ...] = ()

    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output:
        self.last_call = None
        self.last_request = request
        validate_model_id(request.model_id, self._allowed_models)
        if (
            request.budget.max_turns < 1
            or request.budget.max_tool_calls < 0
            or request.budget.max_wall_seconds < 1
        ):
            raise BudgetExhaustedError("model budget is exhausted before execution")
        providers = request.provider_allowlist or tuple(sorted(self._allowed_providers))
        self.last_provider_allowlist = providers
        if (
            providers
            and self._allowed_providers
            and not set(providers).issubset(self._allowed_providers)
        ):
            raise ValueError("request contains an unknown provider")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.task},
        ]
        repair_used = False
        tool_call_count = 0
        billed_cost = 0.0
        deadline = monotonic() + request.budget.max_wall_seconds
        for _turn in range(request.budget.max_turns):
            remaining_seconds = deadline - monotonic()
            if remaining_seconds <= 0:
                raise BudgetExhaustedError("model wall-time budget exhausted")
            request_payload: dict[str, Any] = {
                "model": request.model_id,
                "messages": messages,
                "response_format": {"type": "json_object"},
                "provider": {
                    "allow_fallbacks": False if request.evaluation else len(providers) != 1,
                    "data_collection": "deny",
                    **({"order": list(providers)} if providers else {}),
                },
                "metadata": {"run_id": str(request.run_id), "role": request.role},
            }
            if request.tools is not None:
                request_payload["tools"] = request.tools.definitions()
            response = self._client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=request_payload,
                timeout=max(0.001, min(60.0, remaining_seconds)),
            )
            response.raise_for_status()
            if monotonic() > deadline:
                raise BudgetExhaustedError("model wall-time budget exhausted")
            payload = response.json()
            call_metadata = _metadata(payload)
            billed_cost += call_metadata.billed_cost
            self.last_call = ModelCallMetadata(
                call_metadata.provider,
                call_metadata.usage,
                billed_cost,
                call_metadata.response_id,
            )
            if (
                providers
                and self.last_call.provider != "unknown"
                and self.last_call.provider not in providers
            ):
                raise ValueError("provider response came from outside the configured allowlist")
            if self.last_call.billed_cost > request.budget.max_usd:
                raise BudgetExhaustedError("provider billed cost exceeded the run budget")
            message = _message(payload)
            tool_calls = message.get("tool_calls")
            if isinstance(tool_calls, list) and tool_calls:
                if request.tools is None:
                    raise ValueError("model requested a tool when no registry was provided")
                if tool_call_count + len(tool_calls) > request.budget.max_tool_calls:
                    raise BudgetExhaustedError("tool call budget exhausted")
                messages.append(message)
                for tool_call in tool_calls:
                    tool_call_count += 1
                    tool_id, tool_name, arguments = _tool_request(tool_call)
                    tool_result = request.tools.execute(tool_name, arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_id,
                            "content": json.dumps(tool_result, sort_keys=True),
                        }
                    )
                continue
            content = _content(payload)
            try:
                return output_type.model_validate_json(content)
            except ValidationError as error:
                if repair_used:
                    raise ValueError("model output failed schema repair") from error
                repair_used = True
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": "Return only corrected JSON matching this schema error: "
                        + json.dumps(error.errors(include_input=False)),
                    }
                )
        raise BudgetExhaustedError("model turn budget exhausted")


class PydanticAIModelGateway:
    """Production Pydantic AI adapter for typed output and bounded snapshot tools."""

    def __init__(
        self,
        api_key: str,
        allowed_models: frozenset[str],
        allowed_providers: frozenset[str] = frozenset(),
        client: httpx.AsyncClient | None = None,
        trace_exporter: TraceExporter | None = None,
    ) -> None:
        self._provider = OpenRouterProvider(api_key=api_key, http_client=client)
        self._allowed_models = allowed_models
        self._allowed_providers = allowed_providers
        self.last_call: ModelCallMetadata | None = None
        self.last_request: ModelRequest | None = None
        self.last_provider_allowlist: tuple[str, ...] = ()
        self.trace_exporter = trace_exporter

    def run_agent_loop(self, request: ModelRequest, output_type: type[Output]) -> Output:
        self.last_call = None
        self.last_request = request
        validate_model_id(request.model_id, self._allowed_models)
        providers = request.provider_allowlist or tuple(sorted(self._allowed_providers))
        self.last_provider_allowlist = providers
        if (
            providers
            and self._allowed_providers
            and not set(providers).issubset(self._allowed_providers)
        ):
            raise ValueError("request contains an unknown provider")
        tools = _pydantic_tools(request.tools)
        model = OpenRouterChatModel(
            request.model_id,
            provider=self._provider,
            profile=OpenAIModelProfile(
                supports_tools=True,
                default_structured_output_mode="prompted",
            ),
        )
        agent = Agent(
            model,
            output_type=PromptedOutput(output_type),
            system_prompt=request.system_prompt,
            tools=tools,
            retries=1,
            model_settings={
                "timeout": request.budget.max_wall_seconds,
                "extra_body": {
                    "provider": {
                        "allow_fallbacks": False if request.evaluation else len(providers) != 1,
                        "data_collection": "deny",
                        **({"order": list(providers)} if providers else {}),
                    },
                    "metadata": {"run_id": str(request.run_id), "role": request.role},
                },
            },
        )
        started = monotonic()
        usage = RunUsage()
        try:
            result = agent.run_sync(
                request.task,
                usage_limits=UsageLimits(
                    request_limit=request.budget.max_turns,
                    tool_calls_limit=request.budget.max_tool_calls,
                ),
                usage=usage,
            )
        except UsageLimitExceeded as error:
            self.last_call = _pydantic_call_metadata(model, usage)
            _validate_returned_providers(model, providers)
            raise BudgetExhaustedError(str(error)) from error
        except ModelHTTPError as error:
            self.last_call = _pydantic_call_metadata(model, usage)
            _validate_returned_providers(model, providers)
            raise ModelGatewayError(_safe_provider_error(error)) from error
        except UnexpectedModelBehavior as error:
            self.last_call = _pydantic_call_metadata(model, usage)
            _validate_returned_providers(model, providers)
            raise ModelGatewayError(_safe_model_behavior_error(error)) from error
        response = result.response
        self.last_call = _pydantic_call_metadata(
            model,
            usage,
            response.provider_response_id,
        )
        _validate_returned_providers(model, providers)
        if monotonic() - started > request.budget.max_wall_seconds:
            raise BudgetExhaustedError("model wall-time budget exhausted")
        if self.last_call is not None and self.last_call.billed_cost > request.budget.max_usd:
            raise BudgetExhaustedError("provider billed cost exceeded the run budget")
        return output_type.model_validate(result.output)


def _pydantic_call_metadata(
    model: OpenRouterChatModel,
    usage: RunUsage,
    response_id: str | None = None,
) -> ModelCallMetadata | None:
    details = model.recorded_provider_details
    if usage.requests == 0 and not details:
        return None
    returned_providers = [
        str(detail["provider"])
        for detail in details
        if isinstance(detail.get("provider"), str)
    ]
    actual_provider = returned_providers[-1] if returned_providers else "unknown"
    billed_cost = sum(_float_cost(detail.get("cost", 0.0)) for detail in details)
    return ModelCallMetadata(
        actual_provider,
        {
            "requests": usage.requests,
            "tool_calls": usage.tool_calls,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        billed_cost,
        response_id,
    )


def _validate_returned_providers(
    model: OpenRouterChatModel, providers: tuple[str, ...]
) -> None:
    returned_providers = [
        str(detail["provider"])
        for detail in model.recorded_provider_details
        if isinstance(detail.get("provider"), str)
    ]
    if providers and any(provider not in providers for provider in returned_providers):
        raise ValueError("provider response came from outside the configured allowlist")


def _pydantic_tools(registry: SnapshotToolRegistry | None) -> list[Any]:
    if registry is None:
        return []

    def list_tree(ctx: RunContext[Any], prefix: str = "", depth: int = 8) -> dict[str, Any]:
        return registry.execute(
            "list_tree",
            {"prefix": prefix, "depth": depth},
            model_requests=ctx.usage.requests,
        )

    def read_file(
        ctx: RunContext[Any], path: str, start_line: int = 1, end_line: int = 200
    ) -> dict[str, Any]:
        return registry.execute(
            "read_file",
            {"path": path, "start_line": start_line, "end_line": end_line},
            model_requests=ctx.usage.requests,
        )

    def search_text(
        ctx: RunContext[Any],
        query: str,
        path_prefix: str = "",
        regex: bool = False,
        limit: int = 30,
    ) -> dict[str, Any]:
        return registry.execute(
            "search_text",
            {"query": query, "path_prefix": path_prefix, "regex": regex, "limit": limit},
            model_requests=ctx.usage.requests,
        )

    def search_structure(
        ctx: RunContext[Any],
        symbol: str,
        language: str = "python",
        path_prefix: str = "",
        limit: int = 30,
    ) -> dict[str, Any]:
        return registry.execute(
            "search_structure",
            {
                "symbol": symbol,
                "language": language,
                "path_prefix": path_prefix,
                "limit": limit,
            },
            model_requests=ctx.usage.requests,
        )

    def git_history(
        ctx: RunContext[Any], path_prefix: str = "", limit: int = 20
    ) -> dict[str, Any]:
        return registry.execute(
            "git_history",
            {"path_prefix": path_prefix, "limit": limit},
            model_requests=ctx.usage.requests,
        )

    return [list_tree, read_file, search_text, search_structure, git_history]


def _content(payload: dict[str, Any]) -> str:
    message = _message(payload)
    content = message.get("content")
    if isinstance(content, str):
        return content
    if content is not None:
        return json.dumps(content)
    raise ValueError("provider response has no assistant content")


def _message(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        message = payload["choices"][0]["message"]
    except (IndexError, KeyError, TypeError) as error:
        raise ValueError("provider response has no assistant message") from error
    if not isinstance(message, dict):
        raise ValueError("provider assistant message is invalid")
    return message


def _tool_request(tool_call: object) -> tuple[str, str, dict[str, Any]]:
    if not isinstance(tool_call, dict):
        raise ValueError("provider tool call is invalid")
    tool_id = tool_call.get("id")
    function = tool_call.get("function")
    if not isinstance(tool_id, str) or not isinstance(function, dict):
        raise ValueError("provider tool call is invalid")
    name = function.get("name")
    raw_arguments = function.get("arguments", "{}")
    if not isinstance(name, str) or not isinstance(raw_arguments, str):
        raise ValueError("provider tool call is invalid")
    try:
        arguments = json.loads(raw_arguments)
    except json.JSONDecodeError:
        arguments = {"_invalid_json": True}
    if not isinstance(arguments, dict):
        arguments = {"_invalid_shape": True}
    return tool_id, name, arguments


def _metadata(payload: dict[str, Any]) -> ModelCallMetadata:
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    provider = payload.get("provider")
    if not isinstance(provider, str) or not provider:
        provider = "unknown"
    cost = usage.get("cost", payload.get("cost", 0.0))
    try:
        billed_cost = float(cost or 0.0)
    except (TypeError, ValueError):
        billed_cost = 0.0
    response_id = payload.get("id") if isinstance(payload.get("id"), str) else None
    return ModelCallMetadata(provider, dict(usage), billed_cost, response_id)


def _float_cost(value: object) -> float:
    try:
        return float(value or 0.0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _safe_provider_error(error: ModelHTTPError) -> str:
    body = error.body
    details: object = body
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        details = body["error"]
    code: object = error.status_code
    message: object = "provider request failed"
    if isinstance(details, dict):
        code = details.get("code", code)
        message = details.get("message", message)
    safe_code = str(code)[:100] if isinstance(code, (int, str)) else str(error.status_code)
    safe_message = (
        str(message)[:500] if isinstance(message, (int, str)) else "provider request failed"
    )
    redaction = redact(safe_message)
    if redaction.detected:
        safe_message = "provider error detail redacted"
    else:
        safe_message = redaction.text
    return f"provider HTTP {error.status_code}; code={safe_code}; message={safe_message}"


def _safe_model_behavior_error(error: UnexpectedModelBehavior) -> str:
    message = str(error).splitlines()[0][:300]
    cause = error.__cause__
    if cause is None:
        detail = "none"
    else:
        cause_message = str(cause).splitlines()[0][:200]
        detail = f"{type(cause).__name__}: {cause_message}"
    redaction = redact(f"{message}; cause={detail}")
    safe_detail = (
        "provider error detail redacted" if redaction.detected else redaction.text
    )
    return f"unexpected model behavior; {safe_detail}"
