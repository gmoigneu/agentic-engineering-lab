import json
from pathlib import Path
from runpy import run_path

from agentic_lab.domain.enums import AgentRole
from agentic_lab.evaluation.batch import load_role_dataset

_MATERIALIZER = run_path("scripts/materialize_evaluation_fixtures.py", run_name="fixture_module")
SCENARIOS = _MATERIALIZER["SCENARIOS"]
materialize = _MATERIALIZER["materialize"]


def test_materializer_freezes_live_identity_for_all_role_splits(tmp_path: Path) -> None:
    cases = []
    for index, case_id in enumerate(SCENARIOS, start=1):
        cases.append(
            {
                "case_id": case_id,
                "split": "development" if case_id.startswith("dev-") else "held_out",
                "branch": f"evaluation/{case_id}",
                "base_sha": "b" * 40,
                "head_sha": f"{index:040x}",
                "pull_number": index,
                "pull_url": f"https://example.invalid/pull/{index}",
            }
        )
    seed = tmp_path / "seed.json"
    seed.write_text(
        json.dumps(
            {
                "repository": "gmoigneu/agentic-engineering-lab-eval",
                "repository_id": 1303663681,
                "cases": cases,
            }
        )
    )

    by_sha = {case["head_sha"]: case for case in cases}

    def run(arguments: list[str]) -> str:
        sha = next(sha for sha in by_sha if sha in arguments[2])
        case = by_sha[sha]
        return json.dumps(
            {
                "check_runs": [
                    {
                        "id": 10_000 + case["pull_number"],
                        "name": "test",
                        "head_sha": sha,
                        "status": "completed",
                        "conclusion": "failure",
                        "started_at": "2026-07-17T00:00:00Z",
                        "completed_at": "2026-07-17T00:01:00Z",
                        "details_url": "https://example.invalid/check",
                        "app": {"slug": "github-actions"},
                    }
                ]
            }
        )

    fixtures = tmp_path / "fixtures"
    evidence = tmp_path / "evidence.json"
    materialize(seed, fixtures, evidence, run=run)

    for role in AgentRole:
        dataset = load_role_dataset(
            fixtures / role.value / "development",
            fixtures / role.value / "held-out",
            role,
        )
        assert len(dataset.development) == len(dataset.held_out) == 5
        assert all(case.base_sha == "b" * 40 for case in dataset.development)
        assert all(case.check_run_id > 10_000 for case in dataset.held_out)

    held_scout = load_role_dataset(
        fixtures / "scout" / "development",
        fixtures / "scout" / "held-out",
        AgentRole.SCOUT,
    ).held_out[0]
    assert "pull_request_number" not in held_scout.agent_input()
    assert "check_run_id" not in held_scout.agent_input()
    assert json.loads(evidence.read_text())["checks"][0]["check_run_id"] == 10_001
