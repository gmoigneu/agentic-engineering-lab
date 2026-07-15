from agentic_lab.agents.ci import classify_failure


def test_failure_taxonomy_is_conservative() -> None:
    assert classify_failure("HTTP 403 permission denied") == "permission"
    assert classify_failure("network timeout contacting package registry") == "external"
    assert classify_failure("assertion failed") == "repository"
