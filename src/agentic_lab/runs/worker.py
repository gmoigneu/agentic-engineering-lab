"""Minimal durable worker loop for Milestone 1.

It leases work only. Agent execution is introduced in the scout vertical slice.
"""

from __future__ import annotations

import socket
import time

from agentic_lab.config.settings import get_settings
from agentic_lab.db.session import build_session_factory
from agentic_lab.domain.enums import RunStatus
from agentic_lab.runs.leases import claim_next_run
from agentic_lab.runs.service import transition_run


def main() -> None:
    settings = get_settings()
    sessions = build_session_factory(settings.database_url)
    worker_id = f"worker:{socket.gethostname()}"
    while True:
        with sessions.begin() as session:
            run = claim_next_run(session, worker_id, settings.lease_seconds)
            if run is not None:
                # Provider and repository adapters are injected by deployment wiring.
                # Until configured, preserve an auditable terminal outcome rather than
                # silently leasing work forever.
                transition_run(session, run, RunStatus.FAILED, "worker_not_configured", worker_id)
        time.sleep(1)


if __name__ == "__main__":
    main()
