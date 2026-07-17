from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol

from agentic_lab.gateway.redaction import redact


class TraceSink(Protocol):
    def emit(self, trace_id: str, name: str, payload: dict[str, object]) -> None: ...


class LangfuseClient(Protocol):
    def start_as_current_observation(self, **kwargs: Any) -> Any: ...

    def flush(self) -> None: ...


@dataclass(frozen=True)
class LangfuseTraceSink:
    client: LangfuseClient

    def emit(self, trace_id: str, name: str, payload: dict[str, object]) -> None:
        with self.client.start_as_current_observation(
            name=name,
            as_type="generation",
            trace_context={"trace_id": trace_id},
            metadata=payload,
        ):
            pass
        self.client.flush()


@dataclass(frozen=True)
class TraceExportResult:
    trace_id: str | None
    content_hash: str
    detector_names: tuple[str, ...]


def trace_id_for_run(run_id: str) -> str:
    """Match Langfuse's deterministic W3C trace-ID derivation."""
    return hashlib.sha256(run_id.encode()).digest()[:16].hex()


@dataclass(frozen=True)
class TraceExporter:
    sink: TraceSink

    def export(self, run_id: str, name: str, text: str) -> TraceExportResult:
        result = redact(text)
        if result.detected:
            return TraceExportResult(None, result.content_hash, result.detector_names)
        trace_id = trace_id_for_run(run_id)
        self.sink.emit(
            trace_id,
            name,
            {
                "text": result.text,
                "content_hash": result.content_hash,
                "redacted": False,
                "run_id": run_id,
            },
        )
        return TraceExportResult(trace_id, result.content_hash, ())
