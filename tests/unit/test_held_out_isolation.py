from agentic_lab.evaluation.fixtures import EvaluationCase


def test_agent_input_excludes_held_out_labels():
    case = EvaluationCase(
        case_id="h",
        role="scout",
        fixture_revision="fixtures-v1",
        repository_id=1,
        base_sha="b" * 40,
        pinned_sha="a" * 40,
        pull_request_number=1,
        check_run_id=2,
        task_input="map",
        source_provenance="fixture",
        expected_evidence=["secret-label"],
        deterministic_assertions=["secret-check"],
        human_rubric="rubric",
        split="held_out",
    )
    assert "expected_evidence" not in case.agent_input()
    assert "deterministic_assertions" not in case.agent_input()
    assert "pull_request_number" not in case.agent_input()
    assert "check_run_id" not in case.agent_input()


def test_agent_input_exposes_only_role_required_live_locators():
    common = {
        "case_id": "case",
        "fixture_revision": "fixtures-v1",
        "repository_id": 1,
        "base_sha": "b" * 40,
        "pinned_sha": "a" * 40,
        "pull_request_number": 7,
        "check_run_id": 8,
        "task_input": "inspect",
        "source_provenance": "fixture",
        "expected_evidence": ["label"],
        "deterministic_assertions": ["assertion"],
        "human_rubric": "rubric",
        "split": "development",
    }

    assessor = EvaluationCase(role="assessor", **common).agent_input()
    ci = EvaluationCase(role="ci", **common).agent_input()

    assert assessor["pull_request_number"] == 7
    assert "check_run_id" not in assessor
    assert ci["pull_request_number"] == 7
    assert ci["check_run_id"] == 8
