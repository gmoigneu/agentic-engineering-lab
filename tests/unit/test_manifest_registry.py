from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.executor.manifest import ExecutionManifest
from agentic_lab.policy.manifest_registry import active_manifest, approve_manifest


def test_manifest_is_loaded_from_lab_database() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    manifest = ExecutionManifest.model_validate(
        {
            "manifest_version": "1",
            "repository_id": 1,
            "repository": "owner/repo",
            "allowed_source_paths": ["src/**"],
            "protected_paths": [],
            "recipes": {},
        }
    )
    with sessionmaker(engine)() as session:
        with session.begin():
            approve_manifest(session, manifest)
        assert active_manifest(session, 1) == manifest
