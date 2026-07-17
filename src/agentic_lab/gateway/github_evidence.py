from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from agentic_lab.gateway.redaction import redact

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(?:\s(?P<section>.*))?$")


class UntrustedEvidenceText(BaseModel):
    locator: str = Field(min_length=1, max_length=2_000)
    text: str = Field(max_length=12_000)
    content_hash: str = Field(min_length=64, max_length=64)
    redacted: bool = False
    truncated: bool = False
    untrusted_source: Literal[True] = True

    @field_validator("content_hash")
    @classmethod
    def hexadecimal_hash(cls, value: str) -> str:
        if any(character not in "0123456789abcdef" for character in value):
            raise ValueError("evidence hash must be lowercase hexadecimal")
        return value


class DiffHunkEvidence(BaseModel):
    locator: str
    header: str
    section: str | None = None
    old_start: int = Field(ge=0)
    old_count: int = Field(ge=0)
    new_start: int = Field(ge=0)
    new_count: int = Field(ge=0)
    body: UntrustedEvidenceText


class DiffFileEvidence(BaseModel):
    path: str = Field(min_length=1, max_length=2_000)
    previous_path: str | None = Field(default=None, max_length=2_000)
    status: Literal["added", "modified", "removed", "renamed", "copied", "changed"]
    additions: int = Field(ge=0)
    deletions: int = Field(ge=0)
    changes: int = Field(ge=0)
    binary: Literal["yes", "no", "unknown"]
    symlink: Literal["yes", "no", "unknown"] = "unknown"
    submodule: Literal["yes", "no", "unknown"] = "unknown"
    patch_hash: str = Field(min_length=64, max_length=64)
    hunks: list[DiffHunkEvidence] = Field(default_factory=list, max_length=200)

    @field_validator("path", "previous_path")
    @classmethod
    def safe_path(cls, value: str | None) -> str | None:
        if value is not None and (
            not value or value.startswith("/") or ".." in value.split("/") or "\x00" in value
        ):
            raise ValueError("diff evidence paths must be repository-relative")
        return value


class PullRequestDiffEvidence(BaseModel):
    schema_version: Literal["diff-evidence-v1"] = "diff-evidence-v1"
    repository_id: int = Field(gt=0)
    pull_number: int = Field(gt=0)
    base_sha: str = Field(min_length=40, max_length=64)
    head_sha: str = Field(min_length=40, max_length=64)
    head_ref: str = Field(min_length=1, max_length=255)
    same_repository: bool
    files: list[DiffFileEvidence] = Field(min_length=1, max_length=300)
    truncated: bool = False

    @field_validator("base_sha", "head_sha")
    @classmethod
    def immutable_sha(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("diff evidence requires immutable lowercase SHAs")
        return value


class CheckAnnotationEvidence(BaseModel):
    locator: str
    path: str = Field(min_length=1, max_length=2_000)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    annotation_level: Literal["notice", "warning", "failure"]
    title: str | None = None
    message: UntrustedEvidenceText

    @field_validator("path")
    @classmethod
    def safe_path(cls, value: str) -> str:
        if value.startswith("/") or ".." in value.split("/") or "\x00" in value:
            raise ValueError("check annotation paths must be repository-relative")
        return value


class CheckEvidence(BaseModel):
    schema_version: Literal["check-evidence-v1"] = "check-evidence-v1"
    repository_id: int = Field(gt=0)
    check_run_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    head_sha: str = Field(min_length=40, max_length=64)
    status: Literal["queued", "in_progress", "completed", "pending", "requested", "waiting"]
    conclusion: str | None = None
    app_slug: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    output: list[UntrustedEvidenceText] = Field(default_factory=list, max_length=3)
    log_excerpts: list[UntrustedEvidenceText] = Field(default_factory=list, max_length=3)
    annotations: list[CheckAnnotationEvidence] = Field(default_factory=list, max_length=300)
    annotations_truncated: bool = False
    logs_available: bool = False
    unavailable_signals: list[str] = Field(default_factory=list)

    @field_validator("head_sha")
    @classmethod
    def immutable_sha(cls, value: str) -> str:
        if len(value) not in {40, 64} or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise ValueError("check evidence requires an immutable lowercase SHA")
        return value


def bounded_untrusted_text(
    text: str,
    locator: str,
    *,
    limit: int = 12_000,
    extra_redaction_patterns: tuple[str, ...] = (),
) -> UntrustedEvidenceText:
    encoded = text.encode("utf-8")
    truncated = len(encoded) > limit
    bounded = encoded[:limit].decode("utf-8", errors="ignore")
    result = redact(bounded, extra_redaction_patterns)
    return UntrustedEvidenceText(
        locator=locator,
        text="evidence blocked by redaction policy" if result.detected else result.text,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        redacted=result.detected,
        truncated=truncated,
    )


def parse_diff_hunks(
    patch: str,
    *,
    pull_number: int,
    path: str,
    extra_redaction_patterns: tuple[str, ...] = (),
) -> list[DiffHunkEvidence]:
    hunks: list[DiffHunkEvidence] = []
    header: str | None = None
    body: list[str] = []

    def append_hunk() -> None:
        if header is None:
            return
        match = _HUNK_HEADER.match(header)
        if match is None:
            raise ValueError("GitHub diff contains an invalid hunk header")
        index = len(hunks) + 1
        locator = f"pull_request#{pull_number}:{path}:hunk-{index}"
        hunks.append(
            DiffHunkEvidence(
                locator=locator,
                header=header,
                section=match.group("section") or None,
                old_start=int(match.group(1)),
                old_count=int(match.group(2) or "1"),
                new_start=int(match.group(3)),
                new_count=int(match.group(4) or "1"),
                body=bounded_untrusted_text(
                    "\n".join(body),
                    locator,
                    extra_redaction_patterns=extra_redaction_patterns,
                ),
            )
        )

    for line in patch.splitlines():
        if line.startswith("@@ "):
            append_hunk()
            header = line
            body = []
        elif header is not None:
            body.append(line)
    append_hunk()
    return hunks
