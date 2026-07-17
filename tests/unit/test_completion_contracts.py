from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from agentic_lab.db.base import Base
from agentic_lab.db.models import (
    Artifact,
    Evaluation,
    ModelCall,
    PullRequestOptIn,
    RedactionEvent,
)
from agentic_lab.domain.enums import AgentRole, RunSource, RunStatus
from agentic_lab.domain.schemas import (
    CIDiagnosisArtifact,
    Citation,
    Claim,
    PatchArtifact,
    RecipeEvidence,
    RunCreate,
    TerminalError,
)
from agentic_lab.evaluation.evaluators import citation_resolution
from agentic_lab.evaluation.fixtures import EvaluationCase
from agentic_lab.evaluation.service import store_evaluation
from agentic_lab.executor.manifest import ExecutionManifest, RecipeRequest, validate_recipe_request
from agentic_lab.gateway.model import ScriptedModelGateway
from agentic_lab.policy.patch import PatchPolicy, validate_unified_diff
from agentic_lab.runs.artifacts import store_artifact
from agentic_lab.runs.ci_push import push_validated_patch
from agentic_lab.runs.orchestrator import orchestrate_ci
from agentic_lab.runs.service import create_queued_run, transition_run
from agentic_lab.tools.snapshot import RepositorySnapshot


def test_patch_policy_checks_both_sides_of_a_rename() -> None:
    diff = """diff --git a/src/service.py b/.github/workflows/service.py
--- a/src/service.py
+++ b/.github/workflows/service.py
@@ -1 +1 @@
-old
+new
"""
    result = validate_unified_diff(diff, PatchPolicy(("src/**",), ()))
    assert result.reason_code == "protected_path"
    assert result.changed_paths == (".github/workflows/service.py", "src/service.py")


def test_snapshot_tools_are_bounded_and_resolve_citations() -> None:
    snapshot = RepositorySnapshot("a" * 40, {"src/app.py": "def useful():\n    return 1\n"})
    assert snapshot.search_structure("useful")[0].locator.untrusted
    with pytest.raises(ValueError, match="repository-relative"):
        snapshot.read_file("../secret")
    text = snapshot.read_file("src/app.py", 1, 1).text
    import hashlib

    artifact = CIDiagnosisArtifact(
        run_id=uuid4(),
        role=AgentRole.CI,
        pinned_sha="a" * 40,
        claims=[Claim(id="c1", statement="function exists")],
        citations=[
            Citation(
                claim_id="c1",
                source_kind="file",
                locator="src/app.py#L1-L1",
                pinned_sha="a" * 40,
                excerpt_hash=hashlib.sha256(text.encode()).hexdigest(),
            )
        ],
        failure_class="repository",
        diagnosis="source regression",
    )
    assert citation_resolution(artifact, snapshot).passed


def test_snapshot_locator_hash_matches_the_exact_cited_excerpt() -> None:
    import hashlib

    snapshot = RepositorySnapshot("a" * 40, {"src/app.py": "first line\nsecond line\n"})

    result = snapshot.read_file("src/app.py", 2, 2)

    assert result.locator.content_hash == hashlib.sha256(b"second line").hexdigest()


def test_snapshot_bounds_model_visible_file_and_search_content() -> None:
    snapshot = RepositorySnapshot(
        "a" * 40,
        {
            "large.py": "x" * 40_000,
            "matches.py": "\n".join(f"needle {'y' * 2_000}" for _ in range(60)),
        },
    )

    read = snapshot.read_file("large.py", 1, 1)
    matches = snapshot.search_text("needle", limit=50)

    assert read.truncated
    assert len(read.text.encode()) <= 32_000
    assert len(matches) == 50
    assert all(match.truncated and len(match.text.encode()) <= 1_000 for match in matches)
    with pytest.raises(ValueError, match="oversized line window"):
        snapshot.read_file("matches.py", 1, 201)
    with pytest.raises(ValueError, match="search limit"):
        snapshot.search_text("needle", limit=51)


def test_ci_orchestration_persists_evidence_bearing_refusal() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    with sessions.begin() as session:
        run = create_queued_run(
            session,
            RunCreate(role=AgentRole.CI, repository_id=1, pinned_sha="a" * 40, task_text="fix"),
            RunSource.MANUAL,
            "operator",
        )
        artifact = CIDiagnosisArtifact(
            run_id=run.id,
            role=AgentRole.CI,
            pinned_sha="a" * 40,
            claims=[Claim(id="c1", statement="network timed out")],
            citations=[
                Citation(
                    claim_id="c1",
                    source_kind="check_run",
                    locator="check_run#1:1-2",
                    pinned_sha="a" * 40,
                    excerpt_hash="b" * 64,
                )
            ],
            failure_class="external",
            diagnosis="remote service timed out",
        )
        gateway = ScriptedModelGateway(artifact)
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
        orchestrate_ci(session, run, gateway, "model@1")
        assert run.status is RunStatus.REFUSED
        assert session.query(Artifact).filter_by(run_id=run.id).count() == 2
        assert session.query(ModelCall).filter_by(run_id=run.id).count() == 1


def test_fixture_and_evaluation_records_require_scoring_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        EvaluationCase(
            case_id="case",
            role=AgentRole.SCOUT,
            repository_id=1,
            pinned_sha="a" * 40,
            task_input="map",
            source_provenance="approved fixture",
            expected_evidence=[],
            deterministic_assertions=[],
            human_rubric="",
            split="held_out",
        )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with sessionmaker(engine)() as session:
        with pytest.raises(ValueError, match="dataset split"):
            store_evaluation(session, uuid4(), "secret", "v1", [])
        assert session.query(Evaluation).count() == 0


def test_recipe_contract_rejects_nested_command_keys() -> None:
    manifest = ExecutionManifest.model_validate(
        {
            "manifest_version": "1",
            "repository_id": 1,
            "repository": "owner/repo",
            "allowed_source_paths": ["src/**"],
            "protected_paths": [],
            "recipes": {
                "validate": {
                    "kind": "validate",
                    "image": "image@sha256:" + "a" * 64,
                    "adapter": "noop_v1",
                    "working_directory": "/work/workspace",
                    "arguments_schema": "none_v1",
                    "timeout_seconds": 60,
                    "network": "none",
                }
            },
        }
    )
    with pytest.raises(ValueError, match="command text"):
        validate_recipe_request(
            manifest,
            RecipeRequest("run", "a" * 40, "validate", {"nested": {"script": "curl x"}}),
        )


def test_durable_ci_push_uses_opt_in_and_exact_sha_recheck() -> None:
    import hashlib

    class Writer:
        writes = 0

        def head_sha(self, repository_id: int, branch: str) -> str:
            return "a" * 40

        def apply_unified_diff(
            self, repository_id: int, branch: str, base_sha: str, diff: str, run_id: str
        ) -> str:
            self.writes += 1
            return "c" * 40

    diff = "--- a/src/service.py\n+++ b/src/service.py\n@@ -1 +1 @@\n-old\n+new\n"
    now = datetime.now(UTC)
    evidence = RecipeEvidence(
        recipe_name="validate",
        image_digest="image@sha256:" + "d" * 64,
        exit_code=0,
        started_at=now,
        finished_at=now,
        output_hash="e" * 64,
    )
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    writer = Writer()
    with sessionmaker(engine, expire_on_commit=False).begin() as session:
        run = create_queued_run(
            session,
            RunCreate(role=AgentRole.CI, repository_id=1, pinned_sha="a" * 40, task_text="fix"),
            RunSource.MANUAL,
            "operator",
        )
        run.pull_number = 7
        transition_run(session, run, RunStatus.LEASED, "worker_claimed", "worker")
        transition_run(session, run, RunStatus.RUNNING, "diagnosis_started", "worker")
        transition_run(session, run, RunStatus.EVALUATING, "patch_validated", "worker")
        session.add(
            PullRequestOptIn(
                repository_id=1,
                pull_number=7,
                enabled_by="operator",
                expires_at=now + timedelta(hours=1),
                reason="evaluation",
            )
        )
        artifact = PatchArtifact(
            run_id=run.id,
            role=AgentRole.CI,
            pinned_sha=run.pinned_sha,
            base_sha=run.pinned_sha,
            unified_diff=diff,
            changed_paths=["src/service.py"],
            patch_hash=hashlib.sha256(diff.encode()).hexdigest(),
            reproduction=evidence,
            validation=evidence,
            policy_result="source_only_patch",
        )
        commit = push_validated_patch(
            session,
            run,
            artifact,
            "feature",
            run.pinned_sha,
            True,
            True,
            True,
            "repository",
            writer,
            PatchPolicy(("src/**",), ()),
        )
        assert commit == "c" * 40
        assert writer.writes == 1
        assert run.status is RunStatus.SUCCEEDED


def test_artifact_store_never_persists_detected_secret_value() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    secret = "ghp_" + "z" * 36
    with sessionmaker(engine, expire_on_commit=False).begin() as session:
        run = create_queued_run(
            session,
            RunCreate(
                role=AgentRole.SCOUT,
                repository_id=1,
                pinned_sha="a" * 40,
                task_text="map",
            ),
            RunSource.MANUAL,
            "operator",
        )
        record = store_artifact(
            session,
            TerminalError(
                run_id=run.id,
                role=run.role,
                pinned_sha=run.pinned_sha,
                code="blocked",
                message=f"detected {secret}",
            ),
            "terminal_error",
        )
        assert record.redaction_state == "blocked"
        assert secret not in str(record.content_json)
        assert session.query(RedactionEvent).filter_by(run_id=run.id).count() == 1
