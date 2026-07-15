from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agentic_lab.api.app import create_app
from agentic_lab.config.settings import Settings
from agentic_lab.db.base import Base


def test_manual_run_requires_operator_and_allowlisted_repository() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    app = create_app(
        Settings(
            database_url="sqlite://",
            operator_token="operator",
            github_webhook_secret="webhook",
            allowed_repository_ids=frozenset({123456}),
        ),
        sessions,
    )
    client = TestClient(app)
    payload = {
        "role": "scout",
        "repository_id": 123456,
        "pinned_sha": "a" * 40,
        "task_text": "Map it.",
    }

    assert client.post("/v1/runs", json=payload).status_code == 401
    response = client.post("/v1/runs", json=payload, headers={"X-Operator-Token": "operator"})
    assert response.status_code == 201
    assert response.json()["run"]["status"] == "queued"
    payload["repository_id"] = 654321
    assert (
        client.post("/v1/runs", json=payload, headers={"X-Operator-Token": "operator"}).status_code
        == 403
    )
    payload["repository_id"] = 123456
    payload["budget"] = {"tool_calls": 41}
    assert (
        client.post("/v1/runs", json=payload, headers={"X-Operator-Token": "operator"}).status_code
        == 422
    )
