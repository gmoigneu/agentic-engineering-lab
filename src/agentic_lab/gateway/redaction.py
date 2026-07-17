from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

_PATTERNS = (
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("connection_string", re.compile(r"\b(?:postgres|mysql|mongodb)://[^\s]+", re.I)),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{16,}")),
    (
        "secret_assignment",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret|password|token)\b\s*[:=]\s*['\"]?[A-Za-z0-9_./+=-]{16,}"
        ),
    ),
)


@dataclass(frozen=True)
class RedactionResult:
    text: str
    detected: bool
    detector_names: tuple[str, ...]
    content_hash: str


def redact(text: str, extra_patterns: tuple[str, ...] = ()) -> RedactionResult:
    detected: list[str] = []
    redacted = text
    for name, pattern in _PATTERNS + tuple(
        ("manifest", re.compile(pattern)) for pattern in extra_patterns
    ):
        if pattern.search(redacted):
            detected.append(name)
            redacted = pattern.sub("[REDACTED]", redacted)
    return RedactionResult(
        text=redacted,
        detected=bool(detected),
        detector_names=tuple(detected),
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
