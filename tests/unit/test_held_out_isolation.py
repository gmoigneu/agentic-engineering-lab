from agentic_lab.evaluation.fixtures import EvaluationCase


def test_agent_input_excludes_held_out_labels():
    case = EvaluationCase(
        case_id="h",
        role="scout",
        repository_id=1,
        pinned_sha="a" * 40,
        task_input="map",
        source_provenance="fixture",
        expected_evidence=["secret-label"],
        deterministic_assertions=["secret-check"],
        human_rubric="rubric",
        split="held_out",
    )
    assert "expected_evidence" not in case.agent_input()
    assert "deterministic_assertions" not in case.agent_input()
