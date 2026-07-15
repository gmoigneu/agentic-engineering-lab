from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from agentic_lab.gateway.redaction import redact


class TraceSink(Protocol):
    def emit(self, trace_id: str, name: str, payload: dict[str, object]) -> None: ...


@dataclass(frozen=True)
class TraceExporter:
    sink: TraceSink

    def export(self, run_id: str, name: str, text: str) -> None:
        result = redact(text)
        self.sink.emit(
            run_id,
            name,
            {"text": result.text, "content_hash": result.content_hash, "redacted": result.detected},
        )
