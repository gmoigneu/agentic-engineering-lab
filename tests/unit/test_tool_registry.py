import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local

import agentic_lab.tools.registry as registry_module
from agentic_lab.domain.enums import AgentRole
from agentic_lab.gateway.github_evidence import (
    CheckEvidence,
    DiffFileEvidence,
    PullRequestDiffEvidence,
)
from agentic_lab.tools.registry import SnapshotToolRegistry
from agentic_lab.tools.snapshot import RepositorySnapshot


def test_parallel_tool_calls_receive_unique_monotonic_sequences(monkeypatch) -> None:
    snapshot = RepositorySnapshot("a" * 40, {"file.txt": "content\n"})
    registry = SnapshotToolRegistry(AgentRole.SCOUT, snapshot, max_calls=8)
    barrier = Barrier(8)
    clock_state = local()

    def synchronized_clock() -> float:
        calls = getattr(clock_state, "calls", 0) + 1
        clock_state.calls = calls
        if calls == 2:
            barrier.wait()
        return 0

    monkeypatch.setattr(registry_module, "perf_counter", synchronized_clock)

    def execute(_: int) -> None:
        registry.execute("unknown_tool", {})

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(execute, range(8)))

    assert sorted(record.sequence for record in registry.records) == list(range(1, 9))


def test_evidence_limit_refuses_repository_access_without_exceeding_run_budget() -> None:
    snapshot = RepositorySnapshot("a" * 40, {"file.txt": "content\n"})
    registry = SnapshotToolRegistry(AgentRole.SCOUT, snapshot, max_calls=40)
    registry.configure_evidence_window(max_calls=1, max_requests=8)

    first = registry.execute("list_tree", {})
    second = registry.execute("list_tree", {})

    assert "result" in first
    assert second["error"] == "evidence window closed; return the final artifact"
    assert [record.status for record in registry.records] == ["ok", "policy_refused"]
    assert registry.evidence_available() is False


def test_registry_resolves_a_citation_hash_to_the_exact_tool_locator() -> None:
    snapshot = RepositorySnapshot("a" * 40, {"file.txt": "first\nsecond\n"})
    registry = SnapshotToolRegistry(AgentRole.SCOUT, snapshot, max_calls=2)

    registry.execute("read_file", {"path": "file.txt", "start_line": 2, "end_line": 2})

    assert (
        registry.canonical_locator(
            "file.txt",
            "a" * 40,
            hashlib.sha256(b"second").hexdigest(),
        )
        == "file.txt#L2-L2"
    )


def test_registry_search_default_limits_parallel_context_growth() -> None:
    snapshot = RepositorySnapshot(
        "a" * 40,
        {"file.txt": "\n".join(f"needle {number}" for number in range(100))},
    )
    registry = SnapshotToolRegistry(AgentRole.SCOUT, snapshot, max_calls=1)

    result = registry.execute("search_text", {"query": "needle"})

    assert len(result["result"]) == 30


def test_role_bound_evidence_tools_accept_no_model_selected_resource_id() -> None:
    pinned_sha = "a" * 40
    diff = PullRequestDiffEvidence(
        repository_id=1,
        pull_number=7,
        base_sha="b" * 40,
        head_sha=pinned_sha,
        head_ref="feature",
        same_repository=True,
        files=[
            DiffFileEvidence(
                path="src/app.py",
                status="modified",
                additions=1,
                deletions=0,
                changes=1,
                binary="no",
                patch_hash="c" * 64,
            )
        ],
    )
    check = CheckEvidence(
        repository_id=1,
        check_run_id=9,
        name="tests",
        head_sha=pinned_sha,
        status="completed",
        conclusion="failure",
    )
    registry = SnapshotToolRegistry(
        AgentRole.CI,
        RepositorySnapshot(pinned_sha, {"src/app.py": "value = 1\n"}),
        4,
        diff_evidence=diff,
        check_evidence=check,
    )

    definitions = {item["function"]["name"]: item for item in registry.definitions()}
    assert "inspect_diff" in definitions
    assert "inspect_check" in definitions
    assert definitions["inspect_diff"]["function"]["parameters"]["properties"] == {}
    assert registry.execute("inspect_diff", {})["result"]["head_sha"] == pinned_sha
    refused = registry.execute("inspect_check", {"check_run_id": 10})
    assert refused["error_type"] == "ValidationError"
