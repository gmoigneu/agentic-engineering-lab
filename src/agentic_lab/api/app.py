from __future__ import annotations

import json
import secrets
from collections.abc import Generator
from contextlib import asynccontextmanager
from html import escape
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from agentic_lab.api.security import payload_hash, verify_github_signature
from agentic_lab.config.settings import Settings, get_settings
from agentic_lab.db.models import (
    Artifact,
    HumanReview,
    ModelCall,
    Run,
    WebhookEvent,
    WebhookRunLink,
)
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
from agentic_lab.policy.manifest_registry import active_manifest
from agentic_lab.runs.service import (
    RunNotFoundError,
    create_queued_run,
    get_run,
    link_runs,
    list_transitions,
    supersede_active_runs,
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

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail, "request_id": str(request.state.request_id)},
            headers=error.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "detail": error.errors(include_input=False),
                "request_id": str(request.state.request_id),
            },
        )

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
        configuration_errors = request.app.state.settings.readiness_errors()
        if configuration_errors:
            raise HTTPException(
                status_code=503,
                detail={"configuration_errors": list(configuration_errors)},
            )
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
            manifest = active_manifest(session, payload.repository_id)
            if manifest is None and request.app.state.settings.require_target_manifest:
                raise HTTPException(status_code=409, detail="no approved target manifest")
            effective = _with_effective_budget(payload, request.app.state.settings, manifest)
            run = create_queued_run(session, effective, RunSource.MANUAL, "operator")
            run.manifest_version = manifest.manifest_version if manifest else "read-only-v1"
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
    def run_detail(
        run_id: UUID, request: Request, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        try:
            run = get_run(session, run_id)
        except RunNotFoundError as error:
            raise HTTPException(status_code=404, detail="run not found") from error
        detail = _detail(run, list_transitions(session, run.id), session)
        return {"request_id": request.state.request_id, **detail.model_dump(mode="json")}

    @app.get("/v1/runs/{run_id}/artifacts/{kind}")
    def artifact_detail(
        run_id: UUID, kind: str, request: Request, session: Session = Depends(get_session)
    ) -> dict[str, object]:
        artifact = session.scalar(
            select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind)
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="artifact not found")
        return {
            "request_id": request.state.request_id,
            "kind": artifact.kind,
            "schema_version": artifact.schema_version,
            "content": artifact.content_json,
        }

    @app.post("/v1/runs/{run_id}/review", status_code=status.HTTP_201_CREATED)
    def create_review(
        run_id: UUID,
        payload: HumanReviewCreate,
        request: Request,
        _: None = Depends(operator_auth),
        session: Session = Depends(get_session),
    ) -> dict[str, str]:
        with session.begin():
            try:
                get_run(session, run_id)
            except RunNotFoundError as error:
                raise HTTPException(status_code=404, detail="run not found") from error
            session.add(HumanReview(run_id=run_id, **payload.model_dump()))
        return {"status": "recorded", "request_id": str(request.state.request_id)}

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
        artifacts = list(session.scalars(select(Artifact).where(Artifact.run_id == run.id)))
        reviews = list(session.scalars(select(HumanReview).where(HumanReview.run_id == run.id)))
        detail = _detail(run, transitions, session)
        items = "".join(
            f"<li>{escape(str(item.occurred_at))}: "
            f"{escape(item.from_status.value if item.from_status else 'none')} "
            f"to {escape(item.to_status.value)} ({escape(item.reason_code)})</li>"
            for item in transitions
        )
        artifact_sections = "".join(
            f"<h3>{escape(item.kind)}</h3>"
            f"<pre>{escape(json.dumps(item.content_json, indent=2))}</pre>"
            for item in artifacts
        )
        trace_link = "none"
        trace_host = app.state.settings.langfuse_host
        if trace_host and detail.langfuse_trace_id:
            trace_url = f"{trace_host.rstrip('/')}/trace/{detail.langfuse_trace_id}"
            trace_link = f"<a href='{escape(trace_url)}'>{escape(detail.langfuse_trace_id)}</a>"
        return HTMLResponse(
            f"<html><body><h1>Run {run.id}</h1><p>Status: {escape(run.status.value)}</p>"
            f"<p>Pinned SHA: {escape(run.pinned_sha)}</p>"
            f"<p>Event: {escape(detail.event_delivery_id or 'manual')}</p>"
            f"<p>Trace: {trace_link}</p><h2>Transitions</h2>"
            f"<ul>{items}</ul><h2>Artifacts</h2>"
            f"{artifact_sections or '<p>none</p>'}"
            f"<h2>Reviews</h2><p>{len(reviews)}</p></body></html>"
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


def _with_effective_budget(payload: RunCreate, settings: Settings, manifest: object) -> RunCreate:
    budget = _effective_budget(settings, manifest, payload.budget)
    for name, requested in payload.budget.items():
        if requested > budget[name]:
            raise HTTPException(status_code=422, detail="budget exceeds target manifest maximum")
    return payload.model_copy(update={"budget": budget})


def _effective_budget(
    settings: Settings, manifest: object, requested: dict[str, int | float]
) -> dict[str, int | float]:
    global_limits: dict[str, int | float] = {
        "model_turns": settings.max_model_turns,
        "tool_calls": settings.max_tool_calls,
        "wall_seconds": settings.max_wall_seconds,
        "usd": settings.max_usd,
    }
    manifest_budgets = getattr(manifest, "budgets", None)
    manifest_limits: dict[str, int | float] = {
        "model_turns": getattr(manifest_budgets, "max_model_turns", settings.max_model_turns),
        "tool_calls": getattr(manifest_budgets, "max_tool_calls", settings.max_tool_calls),
        "wall_seconds": getattr(manifest_budgets, "max_wall_seconds", settings.max_wall_seconds),
        "usd": getattr(manifest_budgets, "max_usd", settings.max_usd),
    }
    ceilings = {name: min(global_limits[name], manifest_limits[name]) for name in global_limits}
    return {name: requested.get(name, ceiling) for name, ceiling in ceilings.items()}


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
        _record_safe_rejection(session, delivery_id, event_name, raw_body, "invalid_json")
        raise HTTPException(status_code=400, detail="invalid JSON payload") from error
    repository_id = _repository_id(payload)
    try:
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
            manifest = (
                active_manifest(session, repository_id) if repository_id is not None else None
            )
            if manifest is None and settings.require_target_manifest:
                run, reason = None, "missing_target_manifest"
            else:
                run, reason = _queue_webhook_run(
                    session, event_name, payload, repository_id, settings, source
                )
                if run is not None:
                    run.manifest_version = manifest.manifest_version if manifest else "read-only-v1"
                    run.budget = _effective_budget(settings, manifest, run.budget)
                    session.add(WebhookRunLink(webhook_event_id=event.id, run_id=run.id))
            event.rejection_reason = reason
    except IntegrityError:
        session.rollback()
        return WebhookResponse(request_id=uuid4(), accepted=True, duplicate=True)
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
        if payload.get("action") not in {None, "completed"}:
            return None, "check_run_not_completed"
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
    pull_number = pull_request.get("number", payload.get("number"))
    if not isinstance(pull_number, int) or pull_number < 1:
        pull_number = None
    try:
        data = RunCreate(
            role=AgentRole.ASSESSOR,
            repository_id=repository_id,
            pinned_sha=head["sha"],
            task_text="Assess pull-request risk from verified webhook intake.",
        )
    except ValidationError:
        return None, "invalid_head_sha"
    superseded = []
    sender = payload.get("sender")
    if pull_number is not None and (not isinstance(sender, dict) or sender.get("type") != "Bot"):
        superseded = supersede_active_runs(
            session, repository_id, pull_number, head["sha"], "github_webhook"
        )
    run = create_queued_run(session, data, source, "github_webhook")
    run.pull_number = pull_number
    for previous in superseded:
        link_runs(session, previous, run, "superseded_by")
    return run, None


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
    pull_number = pull_request.get("number")
    if not isinstance(pull_number, int) or pull_number < 1:
        return None, "missing_pull_number"
    head_repository = (
        pull_request.get("head", {}).get("repo")
        if isinstance(pull_request.get("head"), dict)
        else None
    )
    if isinstance(head_repository, dict) and head_repository.get("id") != repository_id:
        return None, "fork_branch_refused"
    existing = session.scalar(
        select(Run).where(
            Run.role == AgentRole.CI,
            Run.repository_id == repository_id,
            Run.pull_number == pull_number,
            Run.pinned_sha == head_sha,
            Run.status.not_in({RunStatus.SUPERSEDED, RunStatus.CANCELLED}),
        )
    )
    if existing is not None:
        return None, "duplicate_ci_head_sha"
    try:
        data = RunCreate(
            role=AgentRole.CI,
            repository_id=repository_id,
            pinned_sha=head_sha,
            task_text="Diagnose a verified failed check run.",
        )
    except ValidationError:
        return None, "invalid_head_sha"
    run = create_queued_run(session, data, source, "github_webhook")
    run.pull_number = pull_number
    assessor = session.scalar(
        select(Run)
        .where(
            Run.role == AgentRole.ASSESSOR,
            Run.repository_id == repository_id,
            Run.pull_number == pull_number,
            Run.pinned_sha == head_sha,
        )
        .order_by(Run.created_at.desc())
    )
    if assessor is not None:
        link_runs(session, assessor, run, "failed_check_after_assessment")
    return run, None


def _summary(run: Run) -> RunSummary:
    return RunSummary(
        id=run.id,
        role=run.role,
        source=run.source,
        repository_id=run.repository_id,
        pinned_sha=run.pinned_sha,
        status=run.status,
        created_at=run.created_at,
        terminal_at=run.terminal_at,
        manifest_version=run.manifest_version,
        policy_version=run.policy_version,
    )


def _detail(run: Run, transitions: list[object], session: Session | None = None) -> RunDetail:
    artifacts = (
        list(session.scalars(select(Artifact.kind).where(Artifact.run_id == run.id)))
        if session is not None
        else []
    )
    trace_id = (
        session.scalar(
            select(ModelCall.langfuse_trace_id)
            .where(ModelCall.run_id == run.id)
            .order_by(ModelCall.sequence.desc())
        )
        if session is not None
        else None
    )
    delivery_id = (
        session.scalar(
            select(WebhookEvent.delivery_id)
            .join(WebhookRunLink, WebhookRunLink.webhook_event_id == WebhookEvent.id)
            .where(WebhookRunLink.run_id == run.id)
        )
        if session is not None
        else None
    )
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
        artifacts=artifacts,
        langfuse_trace_id=trace_id,
        event_delivery_id=delivery_id,
    )


def _record_safe_rejection(
    session: Session,
    delivery_id: str,
    event_name: str | None,
    body: bytes,
    reason: str,
) -> None:
    try:
        with session.begin():
            session.add(
                WebhookEvent(
                    delivery_id=delivery_id,
                    event_name=event_name,
                    repository_id=None,
                    payload_hash=payload_hash(body),
                    signature_valid=True,
                    rejection_reason=reason,
                )
            )
    except IntegrityError:
        session.rollback()


app = create_app()
