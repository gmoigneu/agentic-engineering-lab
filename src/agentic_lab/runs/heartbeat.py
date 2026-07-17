from __future__ import annotations

from threading import Event, Thread
from typing import Any

from agentic_lab.runs.leases import heartbeat_lease


class LeaseLostError(RuntimeError):
    pass


class LeaseHeartbeat:
    """Renew one durable lease while its worker attempt is active."""

    def __init__(
        self,
        sessions: Any,
        run_id: object,
        worker_id: str,
        lease_seconds: int,
        interval_seconds: float | None = None,
    ) -> None:
        self._sessions = sessions
        self._run_id = run_id
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._interval_seconds = interval_seconds or max(1.0, lease_seconds / 3)
        if self._interval_seconds <= 0:
            raise ValueError("heartbeat interval must be positive")
        self._stop = Event()
        self._renewed = Event()
        self._lost = Event()
        self._thread: Thread | None = None

    def __enter__(self) -> LeaseHeartbeat:
        if self._thread is not None:
            raise RuntimeError("heartbeat cannot be restarted")
        self._thread = Thread(
            target=self._run,
            name=f"lease-heartbeat:{self._run_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, error_type: object, _error: object, _traceback: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join()
        if error_type is None and self._lost.is_set():
            raise LeaseLostError(f"lease ownership lost for run {self._run_id}")

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def wait_until_renewed(self, timeout: float | None = None) -> bool:
        return self._renewed.wait(timeout)

    def wait_until_lost(self, timeout: float | None = None) -> bool:
        return self._lost.wait(timeout)

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                with self._sessions.begin() as session:
                    renewed = heartbeat_lease(
                        session,
                        self._run_id,
                        self._worker_id,
                        self._lease_seconds,
                    )
            except Exception:
                self._lost.set()
                return
            if not renewed:
                self._lost.set()
                return
            self._renewed.set()
