from __future__ import annotations

from sqlalchemy.orm import Session

from agentic_lab.db.models import PolicyDecision
from agentic_lab.policy.patch import PolicyResult


def record_decision(
    session: Session, run_id: object, policy_name: str, result: PolicyResult
) -> PolicyDecision:
    decision = PolicyDecision(
        run_id=run_id,
        policy_name=policy_name,
        input_hash=result.input_hash,
        outcome=result.outcome,
        reason_code=result.reason_code,
        metadata_json={"changed_paths": list(result.changed_paths)},
    )
    session.add(decision)
    return decision
