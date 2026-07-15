from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_lab.db.models import TargetManifest
from agentic_lab.executor.manifest import ExecutionManifest


def approve_manifest(session: Session, manifest: ExecutionManifest) -> TargetManifest:
    content = manifest.model_dump(mode="json")
    encoded = manifest.model_dump_json().encode()
    record = TargetManifest(
        repository_id=manifest.repository_id,
        version=manifest.manifest_version,
        content=content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
    )
    session.add(record)
    return record


def active_manifest(session: Session, repository_id: int) -> ExecutionManifest | None:
    record = session.scalar(
        select(TargetManifest)
        .where(TargetManifest.repository_id == repository_id, TargetManifest.retired_at.is_(None))
        .order_by(TargetManifest.approved_at.desc())
    )
    return ExecutionManifest.model_validate(record.content) if record else None
