import json
from pathlib import Path

import pytest

from agentic_lab.domain.enums import AgentRole
from agentic_lab.evaluation.batch import (
    BatchConfiguration,
    CaseResult,
    ProviderPolicy,
    export_scorecard,
    held_out_complete,
    load_cases,
    load_role_dataset,
    validate_comparison,
)


def _fixture(case_id: str, split: str, role: str = "scout") -> dict[str, object]:
    return {
        "case_id": case_id,
        "role": role,
        "repository_id": 1,
        "pinned_sha": "a" * 40,
        "task_input": "map",
        "source_provenance": "fixture",
        "expected_evidence": ["a.py"],
        "deterministic_assertions": ["schema"],
        "human_rubric": "good",
        "split": split,
    }


def _configuration(model_id: str = "model@1", split: str = "development"):
    return BatchConfiguration(
        batch_id=f"batch-{model_id}",
        role=AgentRole.SCOUT,
        split=split,
        model_id=model_id,
        provider_policy=ProviderPolicy(provider_allowlist=("StreamLake",)),
        prompt_hash="a" * 64,
        tool_definitions_hash="b" * 64,
        manifest_version="read-only-v1",
        policy_version="v1",
        evaluator_version="v1",
        fixture_revision="fixture-1",
        label_version="labels-1",
        repository_scope=(1,),
        limitations=("single repository",),
    )


def test_fixture_loader_and_scorecard(tmp_path: Path) -> None:
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    for index in range(5):
        (fixtures / f"case-{index}.json").write_text(
            json.dumps(_fixture(f"case-{index}", "development"))
        )
    cases = load_cases(fixtures, "development")
    output = tmp_path / "scorecard.json"
    export_scorecard(
        [
            CaseResult(
                case.case_id,
                "development",
                True,
                "succeeded",
                {"schema": True},
                run_id=f"run-{index}",
                provider="StreamLake",
                billed_cost=0.01,
                latency_ms=100,
            )
            for index, case in enumerate(cases)
        ],
        output,
        _configuration(),
    )
    payload = json.loads(output.read_text())
    assert payload["success_rate"] == 1.0
    assert payload["task_count"] == 5
    assert payload["configuration"]["provider_policy"]["allow_fallbacks"] is False
    assert payload["failure_categories"] == {
        "evaluator": 0,
        "infrastructure": 0,
        "model": 0,
        "policy": 0,
    }


def test_role_dataset_requires_five_cases_in_each_isolated_split(tmp_path: Path) -> None:
    development = tmp_path / "development"
    held_out = tmp_path / "held-out"
    development.mkdir()
    held_out.mkdir()
    for index in range(5):
        (development / f"dev-{index}.json").write_text(
            json.dumps(_fixture(f"dev-{index}", "development"))
        )
        (held_out / f"held-{index}.json").write_text(
            json.dumps(_fixture(f"held-{index}", "held_out"))
        )

    dataset = load_role_dataset(development, held_out, AgentRole.SCOUT)

    assert len(dataset.development) == 5
    assert len(dataset.held_out) == 5


def test_held_out_scorecard_requires_review_for_every_case(tmp_path: Path) -> None:
    results = [
        CaseResult(f"case-{index}", "held_out", True, "succeeded", {})
        for index in range(5)
    ]
    assert not held_out_complete(results, set())
    assert held_out_complete(results, {item.case_id for item in results})

    with pytest.raises(ValueError, match="human review"):
        export_scorecard(results, tmp_path / "scorecard.json", _configuration(split="held_out"))


def test_model_comparison_requires_exactly_three_pinned_candidates() -> None:
    candidates = [_configuration(f"model@{index}") for index in range(1, 4)]

    validate_comparison(candidates)

    with pytest.raises(ValueError, match="exactly three"):
        validate_comparison(candidates[:2])
    with pytest.raises(ValueError, match="latest aliases"):
        validate_comparison([*candidates[:2], _configuration("model-latest")])
