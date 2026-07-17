"""Minimal durable worker loop for Milestone 1.

It leases work only. Agent execution is introduced in the scout vertical slice.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from langfuse import Langfuse

from agentic_lab.config.settings import get_settings
from agentic_lab.db.models import Run
from agentic_lab.db.session import build_session_factory
from agentic_lab.domain.enums import RunStatus
from agentic_lab.gateway.capability import CapabilityGateway
from agentic_lab.gateway.github import GitHubAppBranchWriter, GitHubBranchWriter
from agentic_lab.gateway.github_read import GitHubAppArchiveReader
from agentic_lab.gateway.model import ModelGateway, PydanticAIModelGateway
from agentic_lab.gateway.tracing import LangfuseTraceSink, TraceExporter
from agentic_lab.runs.heartbeat import LeaseHeartbeat, LeaseLostError
from agentic_lab.runs.leases import claim_next_run, release_lease
from agentic_lab.runs.orchestrator import orchestrate_assessor, orchestrate_ci, orchestrate_scout
from agentic_lab.runs.service import transition_run


@dataclass(frozen=True)
class WorkerDependencies:
    model_gateway: ModelGateway | None
    model_id: str | None
    capability_gateway: CapabilityGateway | None = None
    branch_writer: GitHubBranchWriter | None = None


def dispatch_run(session, run, worker_id: str, dependencies: WorkerDependencies) -> None:
    if (
        run.role.value == "scout"
        and dependencies.model_gateway
        and dependencies.model_id
        and dependencies.capability_gateway
    ):
        orchestrate_scout(
            session,
            run,
            dependencies.model_gateway,
            dependencies.model_id,
            dependencies.capability_gateway,
        )
        return
    if run.role.value == "assessor" and dependencies.model_gateway and dependencies.model_id:
        orchestrate_assessor(
            session,
            run,
            dependencies.model_gateway,
            dependencies.model_id,
            dependencies.capability_gateway,
        )
        return
    if run.role.value == "ci" and dependencies.model_gateway and dependencies.model_id:
        orchestrate_ci(
            session,
            run,
            dependencies.model_gateway,
            dependencies.model_id,
            dependencies.capability_gateway,
        )
        return
    transition_run(session, run, RunStatus.FAILED, "worker_role_not_configured", worker_id)


def build_dependencies(settings) -> WorkerDependencies:
    capability_gateway = None
    branch_writer = None
    if settings.github_app_id is not None and settings.github_private_key is not None:
        private_key = settings.github_private_key.get_secret_value()
        capability_gateway = CapabilityGateway(
            GitHubAppArchiveReader(
                settings.github_app_id,
                private_key,
                settings.github_api_url,
            ),
            settings.allowed_repository_ids,
        )
        branch_writer = GitHubAppBranchWriter(
            settings.github_app_id,
            private_key,
            settings.allowed_repository_ids,
            settings.github_api_url,
        )
    if settings.openrouter_api_key is None or not settings.allowed_model_ids:
        return WorkerDependencies(None, None, capability_gateway, branch_writer)
    model_id = sorted(settings.allowed_model_ids)[0]
    if not settings.allowed_provider_ids:
        return WorkerDependencies(None, model_id, capability_gateway, branch_writer)
    trace_exporter = None
    if settings.langfuse_public_key is not None and settings.langfuse_secret_key is not None:
        trace_exporter = TraceExporter(
            LangfuseTraceSink(
                Langfuse(
                    public_key=settings.langfuse_public_key.get_secret_value(),
                    secret_key=settings.langfuse_secret_key.get_secret_value(),
                    base_url=settings.langfuse_host,
                    environment=settings.environment,
                )
            )
        )
    return WorkerDependencies(
        PydanticAIModelGateway(
            settings.openrouter_api_key.get_secret_value(),
            settings.allowed_model_ids,
            allowed_providers=settings.allowed_provider_ids,
            trace_exporter=trace_exporter,
        ),
        model_id,
        capability_gateway,
        branch_writer,
    )


def process_claimed_run(
    sessions,
    run_id,
    worker_id: str,
    lease_seconds: int,
    dependencies: WorkerDependencies,
) -> bool:
    """Process one claimed run and roll back if lease ownership is lost."""
    try:
        with sessions.begin() as session:
            run = session.get(Run, run_id)
            if run is None:
                return False
            with LeaseHeartbeat(sessions, run_id, worker_id, lease_seconds):
                try:
                    dispatch_run(session, run, worker_id, dependencies)
                except Exception as error:
                    if run.status not in {
                        RunStatus.SUCCEEDED,
                        RunStatus.REFUSED,
                        RunStatus.REJECTED,
                        RunStatus.BUDGET_EXHAUSTED,
                        RunStatus.SUPERSEDED,
                        RunStatus.CANCELLED,
                        RunStatus.FAILED,
                    }:
                        transition_run(
                            session,
                            run,
                            RunStatus.FAILED,
                            "unexpected_worker_error",
                            worker_id,
                            {"error_type": type(error).__name__},
                        )
            if not release_lease(session, run_id, worker_id):
                raise LeaseLostError(f"lease ownership lost for run {run_id}")
    except LeaseLostError:
        return False
    return True


def main() -> None:
    settings = get_settings()
    sessions = build_session_factory(settings.database_url)
    worker_id = f"worker:{socket.gethostname()}"
    dependencies = build_dependencies(settings)
    while True:
        run_id = None
        with sessions.begin() as session:
            run = claim_next_run(session, worker_id, settings.lease_seconds)
            if run is not None:
                run_id = run.id
        if run_id is not None:
            process_claimed_run(
                sessions,
                run_id,
                worker_id,
                settings.lease_seconds,
                dependencies,
            )
        time.sleep(1)


if __name__ == "__main__":
    main()
