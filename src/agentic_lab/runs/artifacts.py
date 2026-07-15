from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_lab.db.models import Artifact, CitationRecord
from agentic_lab.domain.schemas import ArtifactBase


def store_artifact(
    session: Session, artifact: ArtifactBase, kind: str, redaction_state: str = "clean"
) -> Artifact:
    content = artifact.model_dump(mode="json")
    encoded = artifact.model_dump_json().encode()
    record = Artifact(
        run_id=artifact.run_id,
        kind=kind,
        schema_version=artifact.schema_version,
        content_json=content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        redaction_state=redaction_state,
    )
    session.add(record)
    session.flush()
    for citation in artifact.citations:
        session.add(CitationRecord(artifact_id=record.id, **citation.model_dump()))
    return record


def get_artifact(session: Session, run_id: object, kind: str) -> Artifact | None:
    return session.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind))
