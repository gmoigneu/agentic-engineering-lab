import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel

from agentic_lab.domain.enums import AgentRole
from agentic_lab.gateway.model import (
    BudgetExhaustedError,
    ModelBudget,
    ModelGatewayError,
    ModelRequest,
    OpenRouterModelGateway,
    PydanticAIModelGateway,
)
from agentic_lab.tools.registry import SnapshotToolRegistry
from agentic_lab.tools.snapshot import RepositorySnapshot


class Output(BaseModel):
    answer: str


def test_pydantic_gateway_exposes_only_safe_provider_http_details() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            json={"error": {"code": 429, "message": "Provider rate limit reached"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(2, 0, 1),
        )

        with pytest.raises(
            ModelGatewayError,
            match="provider HTTP 429; code=429; message=Provider rate limit reached",
        ):
            gateway.run_agent_loop(request, Output)
    finally:
        asyncio.run(client.aclose())


def test_pydantic_gateway_clears_prior_call_metadata_before_a_failed_run() -> None:
    call_count = 0

    def respond(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-success",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "model@1",
                    "provider": "StreamLake",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": '{"answer":"ok"}',
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 7,
                        "total_tokens": 18,
                        "cost": 0.0125,
                    },
                },
            )
        return httpx.Response(
            429,
            json={"error": {"code": 429, "message": "Provider rate limit reached"}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(2, 0, 1),
        )

        assert gateway.run_agent_loop(request, Output).answer == "ok"
        assert gateway.last_call is not None

        with pytest.raises(ModelGatewayError, match="provider HTTP 429"):
            gateway.run_agent_loop(request, Output)

        assert gateway.last_call is None
    finally:
        asyncio.run(client.aclose())


def test_pydantic_gateway_exposes_a_bounded_output_failure_reason() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-invalid",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "not json"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(3, 0, 1),
        )

        with pytest.raises(
            ModelGatewayError,
            match=r"unexpected model behavior; Exceeded maximum output retries \(1\)",
        ):
            gateway.run_agent_loop(request, Output)
    finally:
        asyncio.run(client.aclose())


def test_pydantic_gateway_uses_prompted_output_with_pinned_provider_policy() -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(2, 0, 1),
        )

        assert gateway.run_agent_loop(request, Output).answer == "ok"
    finally:
        asyncio.run(client.aclose())

    assert "response_format" not in requests[0]
    assert requests[0]["provider"] == {  # type: ignore[index]
        "allow_fallbacks": False,
        "data_collection": "deny",
        "order": ["StreamLake"],
    }


def test_pydantic_gateway_records_actual_provider_usage_and_billed_cost() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-priced",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "provider": "StreamLake",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 7,
                    "total_tokens": 18,
                    "cost": 0.0125,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(2, 0, 1),
        )

        assert gateway.run_agent_loop(request, Output).answer == "ok"
    finally:
        asyncio.run(client.aclose())

    assert gateway.last_call is not None
    assert gateway.last_call.provider == "StreamLake"
    assert gateway.last_call.billed_cost == pytest.approx(0.0125)
    assert gateway.last_call.usage == {
        "requests": 1,
        "tool_calls": 0,
        "input_tokens": 11,
        "output_tokens": 7,
    }


def test_pydantic_gateway_sums_cost_across_tool_turns() -> None:
    responses = iter(
        [
            {
                "id": "chatcmpl-tool",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "provider": "StreamLake",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": '{"path":"src/app.py"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                    "cost": 0.01,
                },
            },
            {
                "id": "chatcmpl-final",
                "object": "chat.completion",
                "created": 2,
                "model": "model@1",
                "provider": "StreamLake",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 20,
                    "completion_tokens": 6,
                    "total_tokens": 26,
                    "cost": 0.02,
                },
            },
        ]
    )

    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot("a" * 40, {"src/app.py": "value = 1\n"}),
        40,
    )
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(3, 1, 1),
            tools=tools,
        )

        assert gateway.run_agent_loop(request, Output).answer == "ok"
    finally:
        asyncio.run(client.aclose())

    assert gateway.last_call is not None
    assert gateway.last_call.provider == "StreamLake"
    assert gateway.last_call.billed_cost == pytest.approx(0.03)
    assert gateway.last_call.usage["requests"] == 2
    assert gateway.last_call.usage["input_tokens"] == 30
    assert gateway.last_call.usage["output_tokens"] == 10


def test_pydantic_gateway_preserves_the_exhausted_budget_reason() -> None:
    def respond(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "list_tree",
                                        "arguments": "{}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot("a" * 40, {"src/app.py": "value = 1\n"}),
        40,
    )
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(1, 40, 1),
            tools=tools,
        )

        with pytest.raises(BudgetExhaustedError, match="request_limit of 1"):
            gateway.run_agent_loop(request, Output)
    finally:
        asyncio.run(client.aclose())


def test_pydantic_gateway_refuses_tools_when_the_evidence_window_closes() -> None:
    requests: list[dict[str, object]] = []

    def respond(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        requests.append(body)
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-tool",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "model@1",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "list_tree",
                                            "arguments": "{}",
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )
        if len(requests) == 2:
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-refused-tool",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "model@1",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-2",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": (
                                                '{"path":"src/app.py","start_line":1,'
                                                '"end_line":1}'
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-final",
                "object": "chat.completion",
                "created": 1,
                "model": "model@1",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": '{"answer":"done"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot("a" * 40, {"src/app.py": "value = 1\n"}),
        40,
    )
    tools.configure_evidence_window(max_calls=40, max_requests=1)
    try:
        gateway = PydanticAIModelGateway(
            "secret",
            frozenset({"model@1"}),
            frozenset({"StreamLake"}),
            client=client,
        )
        request = ModelRequest(
            uuid4(),
            "scout",
            "model@1",
            "system",
            "task",
            "hash",
            ModelBudget(4, 40, 1),
            tools=tools,
        )

        assert gateway.run_agent_loop(request, Output).answer == "done"
    finally:
        asyncio.run(client.aclose())

    assert "tools" in requests[0]
    assert "tools" in requests[1]
    assert [record.status for record in tools.records] == ["ok", "policy_refused"]


def test_provider_repairs_one_invalid_response() -> None:
    responses = iter(
        [
            {"choices": [{"message": {"content": "{}"}}]},
            {"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
        ]
    )
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=next(responses)))
    gateway = OpenRouterModelGateway(
        "secret", frozenset({"model@1"}), httpx.Client(transport=transport)
    )
    request = ModelRequest(
        uuid4(), "scout", "model@1", "system", "task", "hash", ModelBudget(2, 1, 1), True
    )
    assert gateway.run_agent_loop(request, Output).answer == "ok"


def test_provider_rejects_unpinned_model() -> None:
    gateway = OpenRouterModelGateway(
        "secret",
        frozenset({"model@1"}),
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))),
    )
    request = ModelRequest(
        uuid4(), "scout", "latest", "system", "task", "hash", ModelBudget(1, 1, 1)
    )
    with pytest.raises(ValueError, match="pinned"):
        gateway.run_agent_loop(request, Output)


def test_provider_executes_only_typed_snapshot_tools() -> None:
    requests: list[httpx.Request] = []
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "read_file",
                                        "arguments": (
                                            '{"path":"src/app.py","start_line":1,"end_line":1}'
                                        ),
                                    },
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"content": '{"answer":"grounded"}'}}]},
        ]
    )

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=next(responses))

    tools = SnapshotToolRegistry(
        AgentRole.SCOUT,
        RepositorySnapshot("a" * 40, {"src/app.py": "value = 1\n"}),
        1,
    )
    gateway = OpenRouterModelGateway(
        "secret", frozenset({"model@1"}), httpx.Client(transport=httpx.MockTransport(respond))
    )
    request = ModelRequest(
        uuid4(),
        "scout",
        "model@1",
        "system",
        "task",
        "hash",
        ModelBudget(2, 1, 1),
        tools=tools,
    )
    assert gateway.run_agent_loop(request, Output).answer == "grounded"
    assert tools.records[0].tool_name == "read_file"
    second_request = json.loads(requests[1].content)
    tool_result = json.loads(second_request["messages"][-1]["content"])
    assert tool_result["untrusted_source"] is True
