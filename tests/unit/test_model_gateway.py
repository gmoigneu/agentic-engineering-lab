from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel

from agentic_lab.gateway.model import ModelBudget, ModelRequest, OpenRouterModelGateway


class Output(BaseModel):
    answer: str


def test_provider_repairs_one_invalid_response() -> None:
    responses = iter([
        {"choices": [{"message": {"content": "{}"}}]},
        {"choices": [{"message": {"content": '{"answer":"ok"}'}}]},
    ])
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=next(responses)))
    gateway = OpenRouterModelGateway("secret", frozenset({"model@1"}), httpx.Client(transport=transport))
    request = ModelRequest(uuid4(), "scout", "model@1", "system", "task", "hash", ModelBudget(2, 1, 1), True)
    assert gateway.run_agent_loop(request, Output).answer == "ok"


def test_provider_rejects_unpinned_model() -> None:
    gateway = OpenRouterModelGateway("secret", frozenset({"model@1"}), httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))))
    request = ModelRequest(uuid4(), "scout", "latest", "system", "task", "hash", ModelBudget(1, 1, 1))
    with pytest.raises(ValueError, match="pinned"):
        gateway.run_agent_loop(request, Output)
