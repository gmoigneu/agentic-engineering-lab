from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

from agentic_lab.evaluation.fixtures import EvaluationCase


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    split: str
    passed: bool
    terminal_status: str
    scores: dict[str, bool]


def load_cases(directory: Path, split: str) -> list[EvaluationCase]:
    cases: list[EvaluationCase] = []
    for path in sorted(directory.glob("*.json")):
        case = EvaluationCase.model_validate_json(path.read_text())
        if case.split != split:
            raise ValueError(f"fixture {path.name} is in the wrong split")
        cases.append(case)
    return cases


def run_batch(
    cases: list[EvaluationCase], execute: Callable[[EvaluationCase], CaseResult]
) -> list[CaseResult]:
    return [execute(case) for case in cases]


def export_scorecard(
    results: list[CaseResult], destination: Path, configuration: dict[str, object]
) -> None:
    if not results:
        raise ValueError("cannot export an empty batch")
    payload = {
        "configuration": configuration,
        "task_count": len(results),
        "terminal_outcomes": {
            status: sum(item.terminal_status == status for item in results)
            for status in {item.terminal_status for item in results}
        },
        "success_rate": sum(item.passed for item in results) / len(results),
        "results": [asdict(item) for item in results],
    }
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def held_out_complete(results: list[CaseResult], reviewed_case_ids: set[str]) -> bool:
    return all(item.case_id in reviewed_case_ids for item in results if item.split == "held_out")
