"""Minimal durable worker loop for Milestone 1.

It leases work only. Agent execution is introduced in the scout vertical slice.
"""

from __future__ import annotations

import socket
import time

from agentic_lab.config.settings import get_settings
from agentic_lab.db.session import build_session_factory
from agentic_lab.runs.leases import claim_next_run


def main() -> None:
    settings = get_settings()
    sessions = build_session_factory(settings.database_url)
    worker_id = f"worker:{socket.gethostname()}"
    while True:
        with sessions.begin() as session:
            claim_next_run(session, worker_id, settings.lease_seconds)
        time.sleep(1)


if __name__ == "__main__":
    main()
