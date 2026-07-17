from __future__ import annotations

from sqlalchemy.orm import Session

from agentic_lab.db.models import Evaluation
from agentic_lab.evaluation.evaluators import EvaluationResult


def store_evaluation(
    session: Session,
    run_id: object,
    dataset_split: str,
    evaluator_version: str,
    results: list[EvaluationResult],
) -> Evaluation:
    if dataset_split not in {"development", "held_out"}:
        raise ValueError("unknown dataset split")
    if not evaluator_version:
        raise ValueError("evaluator version is required")
    record = Evaluation(
        run_id=run_id,
        dataset_split=dataset_split,
        evaluator_version=evaluator_version,
        score_json={
            result.name: {"passed": result.passed, "detail": result.detail} for result in results
        },
        passed=bool(results) and all(result.passed for result in results),
    )
    session.add(record)
    return record
