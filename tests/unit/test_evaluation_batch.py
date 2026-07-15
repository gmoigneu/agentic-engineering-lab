from pathlib import Path

from agentic_lab.evaluation.batch import CaseResult, export_scorecard, held_out_complete, load_cases


def test_fixture_loader_and_scorecard(tmp_path: Path) -> None:
    fixture = {
        "case_id": "one",
        "role": "scout",
        "repository_id": 1,
        "pinned_sha": "a" * 40,
        "task_input": "map",
        "source_provenance": "fixture",
        "expected_evidence": ["a.py"],
        "deterministic_assertions": ["schema"],
        "human_rubric": "good",
        "split": "development",
    }
    (tmp_path / "one.json").write_text(__import__("json").dumps(fixture))
    cases = load_cases(tmp_path, "development")
    output = tmp_path / "scorecard.json"
    export_scorecard(
        [CaseResult(cases[0].case_id, "development", True, "succeeded", {"schema": True})],
        output,
        {"model": "model@1"},
    )
    assert '"success_rate": 1.0' in output.read_text()


def test_held_out_batch_requires_review_for_every_case():
    results = [CaseResult("one", "held_out", True, "succeeded", {})]
    assert not held_out_complete(results, set())
    assert held_out_complete(results, {"one"})
