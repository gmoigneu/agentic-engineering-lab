from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from agentic_lab.api.app import create_app
from agentic_lab.config.settings import Settings
from agentic_lab.db.base import Base
from agentic_lab.db.models import Run, RunLease, WebhookEvent
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import RunCreate
from agentic_lab.runs.leases import claim_next_run, heartbeat_lease
from agentic_lab.runs.service import create_queued_run


def _app() -> tuple[TestClient, sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://",
        operator_token="test-operator-token",
        github_webhook_secret="test-webhook-secret",
        allowed_repository_ids=frozenset({123456}),
    )
    return TestClient(create_app(settings, sessions)), sessions


def _signature(payload: bytes) -> str:
    return "sha256=" + hmac.new(b"test-webhook-secret", payload, hashlib.sha256).hexdigest()


def test_valid_signed_delivery_creates_one_queued_run_and_deduplicates() -> None:
    client, sessions = _app()
    body = (
        b'{"action":"opened","repository":{"id":123456},'
        b'"pull_request":{"head":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}'
    )
    headers = {
        "X-GitHub-Delivery": "delivery-1",
        "X-GitHub-Event": "pull_request",
        "X-Hub-Signature-256": _signature(body),
    }

    response = client.post("/webhooks/github", content=body, headers=headers)
    duplicate = client.post("/webhooks/github", content=body, headers=headers)

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert duplicate.json()["duplicate"] is True
    with sessions() as session:
        assert session.scalar(select(Run).where(Run.status == RunStatus.QUEUED)) is not None
        assert len(list(session.scalars(select(WebhookEvent)))) == 1


def test_invalid_signature_records_safe_metadata_without_a_run() -> None:
    client, sessions = _app()
    body = b'{"repository":{"id":123456}}'
    response = client.post(
        "/webhooks/github",
        content=body,
        headers={"X-GitHub-Delivery": "invalid-delivery", "X-GitHub-Event": "pull_request"},
    )

    assert response.status_code == 401
    with sessions() as session:
        event = session.scalar(select(WebhookEvent))
        assert event is not None
        assert event.signature_valid is False
        assert event.payload_hash == hashlib.sha256(body).hexdigest()
        assert session.scalar(select(Run)) is None


def test_signed_fixture_replay_uses_the_intake_path() -> None:
    client, _ = _app()
    body = (
        '{"action":"opened","repository":{"id":123456},'
        '"pull_request":{"head":{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}}'
    )
    response = client.post(
        "/v1/replays/github",
        json={
            "delivery_id": "replay-1",
            "event_name": "pull_request",
            "body": body,
            "signature": _signature(body.encode()),
        },
        headers={"X-Operator-Token": "test-operator-token"},
    )
    assert response.status_code == 200
    assert response.json()["accepted"] is True


def test_worker_claims_heartbeats_expires_and_reclaims_lease() -> None:
    _, sessions = _app()
    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.SCOUT,
                repository_id=123456,
                pinned_sha="a" * 40,
                task_text="Map a change.",
            ),
            RunSource.MANUAL,
            "operator",
        )
    with sessions.begin() as session:
        claimed = claim_next_run(session, "worker-a", 60)
        assert claimed is not None
        assert claimed.id == run.id
        assert heartbeat_lease(session, run.id, "worker-a", 60)
    with sessions.begin() as session:
        lease = session.get(RunLease, run.id)
        assert lease is not None
        lease.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with sessions.begin() as session:
        reclaimed = claim_next_run(session, "worker-b", 60)
        assert reclaimed is not None
        assert reclaimed.id == run.id
        lease = session.get(RunLease, run.id)
        assert lease is not None
        assert lease.worker_id == "worker-b"
        assert lease.attempt == 2
