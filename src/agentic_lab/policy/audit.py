from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from agentic_lab.db.models import PolicyDecision
from agentic_lab.domain.enums import PolicyOutcome
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


class DatabaseCapabilityAudit:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self, run_id: str, policy_name: str, outcome: str, reason_code: str, input_hash: str
    ) -> None:
        self._session.add(
            PolicyDecision(
                run_id=UUID(run_id),
                policy_name=policy_name,
                input_hash=input_hash,
                outcome=PolicyOutcome(outcome),
                reason_code=reason_code,
                metadata_json={},
            )
        )
