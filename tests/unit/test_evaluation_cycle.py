from pathlib import Path

from agentic_lab.evaluation.cycle import load_cycle_plan


def test_approved_cycle_records_repository_reviewer_budget_and_candidates() -> None:
    plan = load_cycle_plan(Path("evaluation/cycle-v1.json"))

    assert plan.repository_id == 1303663681
    assert plan.reviewer == "gmoigneu"
    assert plan.total_budget_usd == 10
    assert plan.budget_allocation.total == 10
    assert plan.budget_allocation.per_run_max_usd == 0.2
    assert {candidate.model_id for candidate in plan.candidates} == {
        "deepseek/deepseek-v4-flash",
        "qwen/qwen3.7-plus",
        "openai/gpt-5.6-luna",
    }
    assert all(
        candidate.provider_policy.data_collection == "deny"
        and candidate.provider_policy.allow_fallbacks is False
        and len(candidate.provider_policy.provider_allowlist) == 1
        for candidate in plan.candidates
    )
