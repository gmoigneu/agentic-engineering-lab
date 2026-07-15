"""Minimal durable worker loop for Milestone 1.

It leases work only. Agent execution is introduced in the scout vertical slice.
"""

from __future__ import annotations

import socket
import time
from dataclasses import dataclass

from agentic_lab.config.settings import get_settings
from agentic_lab.db.session import build_session_factory
from agentic_lab.domain.enums import RunStatus
from agentic_lab.gateway.model import ModelGateway
from agentic_lab.runs.leases import claim_next_run
from agentic_lab.runs.orchestrator import orchestrate_scout
from agentic_lab.runs.service import transition_run


@dataclass(frozen=True)
class WorkerDependencies:
    model_gateway: ModelGateway | None
    model_id: str | None


def dispatch_run(session, run, worker_id: str, dependencies: WorkerDependencies) -> None:
    if run.role.value == "scout" and dependencies.model_gateway and dependencies.model_id:
        orchestrate_scout(session, run, dependencies.model_gateway, dependencies.model_id)
        return
    transition_run(session, run, RunStatus.FAILED, "worker_role_not_configured", worker_id)


def main() -> None:
    settings = get_settings()
    sessions = build_session_factory(settings.database_url)
    worker_id = f"worker:{socket.gethostname()}"
    dependencies = WorkerDependencies(None, None)
    while True:
        with sessions.begin() as session:
            run = claim_next_run(session, worker_id, settings.lease_seconds)
            if run is not None:
                dispatch_run(session, run, worker_id, dependencies)
        time.sleep(1)


if __name__ == "__main__":
    main()
