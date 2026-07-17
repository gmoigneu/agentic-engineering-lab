from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from agentic_lab.db.models import Artifact, CitationRecord, RedactionEvent
from agentic_lab.domain.schemas import ArtifactBase
from agentic_lab.gateway.redaction import redact


def store_artifact(
    session: Session, artifact: ArtifactBase, kind: str, redaction_state: str = "clean"
) -> Artifact:
    serialized = artifact.model_dump_json()
    redaction = redact(serialized)
    content = (
        {
            "schema_version": artifact.schema_version,
            "run_id": str(artifact.run_id),
            "role": artifact.role.value,
            "pinned_sha": artifact.pinned_sha,
            "created_at": artifact.created_at.isoformat(),
            "claims": [],
            "unknowns": ["artifact content blocked by redaction policy"],
            "citations": [],
            "redaction_blocked": True,
        }
        if redaction.detected
        else artifact.model_dump(mode="json")
    )
    encoded = serialized.encode()
    effective_state = "blocked" if redaction.detected else redaction_state
    record = Artifact(
        run_id=artifact.run_id,
        kind=kind,
        schema_version=artifact.schema_version,
        content_json=content,
        content_hash=hashlib.sha256(encoded).hexdigest(),
        redaction_state=effective_state,
    )
    session.add(record)
    session.flush()
    for citation in content.get("citations", []):
        session.add(CitationRecord(artifact_id=record.id, **citation))
    for detector_name in redaction.detector_names:
        session.add(
            RedactionEvent(
                run_id=artifact.run_id,
                detector_name=detector_name,
                content_hash=redaction.content_hash,
                source_locator=f"artifact:{kind}",
                resolution_state="blocked",
            )
        )
    return record


def get_artifact(session: Session, run_id: object, kind: str) -> Artifact | None:
    return session.scalar(select(Artifact).where(Artifact.run_id == run_id, Artifact.kind == kind))
