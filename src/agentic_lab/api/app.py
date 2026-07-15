from __future__ import annotations

import json
import secrets
from collections.abc import Generator
from contextlib import asynccontextmanager
from html import escape
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agentic_lab.api.security import payload_hash, verify_github_signature
from agentic_lab.config.settings import Settings, get_settings
from agentic_lab.db.models import Artifact, HumanReview, Run, WebhookEvent
from agentic_lab.db.session import build_session_factory
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import (
    GithubReplay,
    HumanReviewCreate,
    RunCreate,
    RunCreateResponse,
    RunDetail,
    RunSummary,
    RunTransitionSummary,
    WebhookResponse,
)
from agentic_lab.runs.service import (
    RunNotFoundError,
    create_queued_run,
    get_run,
    list_transitions,
    transition_run,
)


def create_app(
    settings: Settings | None = None, sessions: sessionmaker[Session] | None = None
) -> FastAPI:
    settings = settings or get_settings()
    sessions = sessions or build_session_factory(settings.database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> Generator[None, None, None]:
        yield

    app = FastAPI(title="Agentic Engineering Lab", lifespan=lifespan)
    app.state.settings = settings
    app.state.sessions = sessions

    def get_session(request: Request) -> Generator[Session, None, None]:
        with request.app.state.sessions() as session:
            yield session

    def operator_auth(
        request: Request,
        x_operator_token: str | None = Header(default=None),
    ) -> None:
        configured = request.app.state.settings.operator_token.get_secret_value()
        if x_operator_token is None or not secrets.compare_digest(x_operator_token, configured):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="operator authentication required"
            )

    @app.middleware("http")
    async def add_request_id(request: Request, call_next: object) -> Response:
        request.state.request_id = uuid4()
        response = await call_next(request)  # type: ignore[operator]
        response.headers["X-Request-ID"] = str(request.state.request_id)
        return response

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        return {"status": "ok", "request_id": str(request.state.request_id)}

    @app.get("/readyz")
    def readyz(request: Request, session: Session = Depends(get_session)) -> dict[str, str]:
        try:
            session.execute(select(1))
        except Exception as error:
            raise HTTPException(status_code=503, detail="database unavailable") from error
        return {"status": "ready", "request_id": str(request.state.request_id)}

    @app.post("/v1/runs", response_model=RunCreateResponse, status_code=status.HTTP_201_CREATED)
    def create_run(
        payload: RunCreate,
        request: Request,
        _: None = Depends(operator_auth),
        session: Session = Depends(get_session),
    ) -> RunCreateResponse:
        _validate_manual_request(payload, request.app.state.settings)
        with session.begin():
            run = create_queued_run(session, payload, RunSource.MANUAL, "operator")
        return RunCreateResponse(request_id=request.state.request_id, run=_summary(run))

    @app.post("/v1/runs/{run_id}/cancel", response_model=RunCreateResponse)
    def cancel_run(
        run_id: UUID,
        request: Request,
        _: None = Depends(operator_auth),
        session: Session = Depends(get_session),
    ) -> RunCreateResponse:
        with session.begin():
            try:
                run = get_run(session, run_id)
            except RunNotFoundError as error:
                raise HTTPException(status_code=404, detail="run not found") from error
            try:
                transition_run(session, run, RunStatus.CANCELLED, "operator_cancelled", "operator")
            except ValueError as error:
                raise HTTPException(status_code=409, detail=str(error)) from error
        return RunCreateResponse(request_id=request.state.request_id, run=_summary(run))

    @app.get("/v1/runs/{run_id}", response_model=RunDetail)
    def run_detail(run_id: UUID, session: Session = Depends(get_session)) -> RunDetail:
        try:
            run = get_run(session, run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="run not found") from error
        return _detail(run, list_transitions(session, run.id))

    @app.get("/v1/runs/{run_id}/artifacts/{kind}")
    def artifact_detail(
        run_id: UUID, kind: str, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        artifact = session.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind)
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return {
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
            "content": artifact.content_json,
        }

    @app.post("/v1/runs/{run_id}/review", status_code=status.HTTP_201_CREATED)
    def create_review(
        run_id: UUID,
        payload: HumanReviewCreate,
        _: None = Depends(operator_auth),
        session: Session = Depends(get_session),
    ) -> dict[str, str]:
        with session.begin():
            try:
                get_run(session, run_id)
            except RunNotFoundError as error:
                raise HTTPException(status_code=404, detail="run not found") from error
            session.add(HumanReview(run_id=run_id, **payload.model_dump()))
        return {"status": "recorded"}

    @app.post("/webhooks/github", response_model=WebhookResponse)
    async def github_webhook(
        request: Request,
        x_github_delivery: str | None = Header(default=None),
        x_github_event: str | None = Header(default=None),
        x_hub_signature_256: str | None = Header(default=None),
        session: Session = Depends(get_session),
    ) -> WebhookResponse:
        raw_body = await request.body()
        result = _process_github_delivery(
            session,
            request.app.state.settings,
            x_github_delivery or f"missing:{payload_hash(raw_body)}",
            x_github_event,
            raw_body,
            x_hub_signature_256,
            RunSource.WEBHOOK,
        )
        if not result.accepted:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        return result.model_copy(update={"request_id": request.state.request_id})

    @app.post("/v1/replays/github", response_model=WebhookResponse)
    def replay_github_fixture(
        replay: GithubReplay,
        request: Request,
        _: None = Depends(operator_auth),
        session: Session = Depends(get_session),
    ) -> WebhookResponse:
        result = _process_github_delivery(
            session,
            request.app.state.settings,
            replay.delivery_id,
            replay.event_name,
            replay.body.encode(),
            replay.signature,
            RunSource.REPLAY,
        )
        if not result.accepted:
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        return result.model_copy(update={"request_id": request.state.request_id})

    @app.get("/", response_class=HTMLResponse)
    def run_list(session: Session = Depends(get_session)) -> HTMLResponse:
        runs = list(session.scalars(select(Run).order_by(Run.created_at.desc()).limit(100)))
        rows = "".join(
            f"<tr><td><a href='/runs/{run.id}'>{run.id}</a></td><td>{escape(run.role.value)}</td>"
            f"<td>{escape(run.status.value)}</td><td>{escape(run.pinned_sha)}</td></tr>"
            for run in runs
        )
        return HTMLResponse(
            "<html><body><h1>Agentic Engineering Lab runs</h1>"
            "<table><thead><tr><th>Run</th><th>Role</th><th>Status</th>"
            "<th>Pinned SHA</th></tr></thead>"
            f"<tbody>{rows}</tbody></table></body></html>"
        )

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(run_id: UUID, session: Session = Depends(get_session)) -> HTMLResponse:
        try:
            run = get_run(session, run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="run not found") from error
        transitions = list_transitions(session, run.id)
        items = "".join(
            f"<li>{escape(str(item.occurred_at))}: "
            f"{escape(item.from_status.value if item.from_status else 'none')} "
            f"to {escape(item.to_status.value)} ({escape(item.reason_code)})</li>"
            for item in transitions
        )
        return HTMLResponse(
            f"<html><body><h1>Run {run.id}</h1><p>Status: {escape(run.status.value)}</p>"
            f"<p>Pinned SHA: {escape(run.pinned_sha)}</p><h2>Transitions</h2>"
            f"<ul>{items}</ul></body></html>"
        )

    return app


def _validate_manual_request(payload: RunCreate, settings: Settings) -> None:
    if payload.repository_id not in settings.allowed_repository_ids:
        raise HTTPException(status_code=403, detail="repository is not allowlisted")
    limits = {
        "model_turns": settings.max_model_turns,
        "tool_calls": settings.max_tool_calls,
        "wall_seconds": settings.max_wall_seconds,
        "usd": settings.max_usd,
    }
    unknown_budget_names = payload.budget.keys() - limits.keys()
    if unknown_budget_names:
        raise HTTPException(status_code=422, detail="budget contains an unknown limit")
    for name, value in payload.budget.items():
        if value < 0:
            raise HTTPException(status_code=422, detail="budget must not be negative")
        if value > limits[name]:
            raise HTTPException(status_code=422, detail="budget exceeds configured maximum")


def _record_invalid_delivery(
    session: Session, delivery_id: str, event_name: str | None, body: bytes
) -> None:
    try:
        with session.begin():
            session.add(
                WebhookEvent(
                    delivery_id=delivery_id,
                    event_name=event_name,
                    repository_id=None,
                    payload_hash=payload_hash(body),
                    signature_valid=False,
                    rejection_reason="invalid_signature",
                )
            )
    except IntegrityError:
        pass


def _process_github_delivery(
    session: Session,
    settings: Settings,
    delivery_id: str,
    event_name: str | None,
    raw_body: bytes,
    signature: str | None,
    source: RunSource,
) -> WebhookResponse:
    if not verify_github_signature(
        raw_body, signature, settings.github_webhook_secret.get_secret_value()
    ):
        _record_invalid_delivery(session, delivery_id, event_name, raw_body)
        return WebhookResponse(request_id=uuid4(), accepted=False)
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="invalid JSON payload") from error
    repository_id = _repository_id(payload)
    with session.begin():
        existing = session.scalar(
            select(WebhookEvent.id).where(WebhookEvent.delivery_id == delivery_id)
        )
        if existing is not None:
            return WebhookResponse(request_id=uuid4(), accepted=True, duplicate=True)
        event = WebhookEvent(
            delivery_id=delivery_id,
            event_name=event_name,
            repository_id=repository_id,
            payload_hash=payload_hash(raw_body),
            signature_valid=True,
        )
        session.add(event)
        session.flush()
        run, reason = _queue_webhook_run(
            session, event_name, payload, repository_id, settings, source
        )
        event.rejection_reason = reason
    return WebhookResponse(request_id=uuid4(), accepted=True, run_id=run.id if run else None)


def _repository_id(payload: object) -> int | None:
    if not isinstance(payload, dict):
        return None
    repository = payload.get("repository")
    if not isinstance(repository, dict) or not isinstance(repository.get("id"), int):
        return None
    return repository["id"]


def _queue_webhook_run(
    session: Session,
    event_name: str | None,
    payload: object,
    repository_id: int | None,
    settings: Settings,
    source: RunSource,
) -> tuple[Run | None, str | None]:
    if repository_id is None:
        return None, "missing_repository_id"
    if repository_id not in settings.allowed_repository_ids:
        return None, "repository_not_allowlisted"
    if not isinstance(payload, dict):
        return None, "unsupported_event"
    if event_name == "check_run":
        return _queue_check_run(session, payload, repository_id, source)
    if event_name != "pull_request":
        return None, "unsupported_event"
    action = payload.get("action")
    pull_request = payload.get("pull_request")
    if action not in {"opened", "synchronize", "reopened"} or not isinstance(pull_request, dict):
        return None, "unsupported_event_action"
    head = pull_request.get("head")
    if not isinstance(head, dict) or not isinstance(head.get("sha"), str):
        return None, "missing_head_sha"
    try:
        data = RunCreate(
            role=AgentRole.ASSESSOR,
            repository_id=repository_id,
            pinned_sha=head["sha"],
            task_text="Assess pull-request risk from verified webhook intake.",
        )
    except ValidationError:
        return None, "invalid_head_sha"
    return create_queued_run(session, data, source, "github_webhook"), None


def _queue_check_run(
    session: Session, payload: dict[object, object], repository_id: int, source: RunSource
) -> tuple[Run | None, str | None]:
    check_run = payload.get("check_run")
    if not isinstance(check_run, dict) or check_run.get("conclusion") != "failure":
        return None, "check_not_failed"
    pull_requests = check_run.get("pull_requests")
    if not isinstance(pull_requests, list) or len(pull_requests) != 1:
        return None, "check_run_without_single_pr"
    pull_request = pull_requests[0]
    if not isinstance(pull_request, dict):
        return None, "check_run_without_single_pr"
    head_sha = check_run.get("head_sha")
    if not isinstance(head_sha, str):
        return None, "missing_head_sha"
    try:
        data = RunCreate(
            role=AgentRole.CI,
            repository_id=repository_id,
            pinned_sha=head_sha,
            task_text="Diagnose a verified failed check run.",
        )
    except ValidationError:
        return None, "invalid_head_sha"
    return create_queued_run(session, data, source, "github_webhook"), None


def _summary(run: Run) -> RunSummary:
    return RunSummary(
        id=run.id,
        role=run.role,
        source=run.source,
        repository_id=run.repository_id,
        pinned_sha=run.pinned_sha,
        status=run.status,
        created_at=run.created_at,
    )


def _detail(run: Run, transitions: list[object]) -> RunDetail:
    return RunDetail(
        **_summary(run).model_dump(),
        transitions=[
            RunTransitionSummary(
                from_status=item.from_status,
                to_status=item.to_status,
                reason_code=item.reason_code,
                actor=item.actor,
                occurred_at=item.occurred_at,
            )
            for item in transitions
        ],
    )


app = create_app()
