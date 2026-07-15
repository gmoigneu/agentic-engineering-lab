from enum import StrEnum


class AgentRole(StrEnum):
    SCOUT = "scout"
    ASSESSOR = "assessor"
    CI = "ci"


class RunSource(StrEnum):
    MANUAL = "manual"
    WEBHOOK = "webhook"
    REPLAY = "replay"


class RunStatus(StrEnum):
    RECEIVED = "received"
    QUEUED = "queued"
    LEASED = "leased"
    SNAPSHOTTING = "snapshotting"
    RUNNING = "running"
    EVALUATING = "evaluating"
    READY_TO_PUSH = "ready_to_push"
    PUSHING = "pushing"
    SUCCEEDED = "succeeded"
    REFUSED = "refused"
    REJECTED = "rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"
    FAILED = "failed"


class PolicyOutcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.REFUSED,
        RunStatus.REJECTED,
        RunStatus.BUDGET_EXHAUSTED,
        RunStatus.SUPERSEDED,
        RunStatus.CANCELLED,
        RunStatus.FAILED,
    }
)

ALLOWED_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.RECEIVED: frozenset({RunStatus.REJECTED, RunStatus.QUEUED}),
    RunStatus.QUEUED: frozenset({RunStatus.LEASED, RunStatus.CANCELLED, RunStatus.SUPERSEDED}),
    RunStatus.LEASED: frozenset({RunStatus.SNAPSHOTTING, RunStatus.RUNNING, RunStatus.FAILED}),
    RunStatus.SNAPSHOTTING: frozenset({RunStatus.RUNNING, RunStatus.REFUSED, RunStatus.FAILED}),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.EVALUATING,
            RunStatus.REFUSED,
            RunStatus.BUDGET_EXHAUSTED,
            RunStatus.FAILED,
            RunStatus.SUPERSEDED,
        }
    ),
    RunStatus.EVALUATING: frozenset(
        {
            RunStatus.READY_TO_PUSH,
            RunStatus.SUCCEEDED,
            RunStatus.REFUSED,
            RunStatus.FAILED,
            RunStatus.SUPERSEDED,
        }
    ),
    RunStatus.READY_TO_PUSH: frozenset(
        {RunStatus.PUSHING, RunStatus.REFUSED, RunStatus.SUPERSEDED}
    ),
    RunStatus.PUSHING: frozenset({RunStatus.SUCCEEDED, RunStatus.REFUSED, RunStatus.FAILED}),
}
