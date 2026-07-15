from __future__ import annotations

from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_lab.agents.assessor import run_assessor
from agentic_lab.agents.scout import run_scout
from agentic_lab.db.models import ModelCall, Run
from agentic_lab.domain.enums import AgentRole, RunStatus
from agentic_lab.gateway.model import ModelBudget, ModelGateway
from agentic_lab.runs.artifacts import store_artifact
from agentic_lab.runs.service import transition_run


def orchestrate_scout(session: Session, run: Run, gateway: ModelGateway, model_id: str) -> None:
    if run.role is not AgentRole.SCOUT or run.status is not RunStatus.LEASED:
        raise ValueError("only leased Scout runs can be orchestrated")
    transition_run(session, run, RunStatus.SNAPSHOTTING, "snapshot_policy_checked", "worker")
    transition_run(session, run, RunStatus.RUNNING, "scout_started", "worker")
    budget = ModelBudget(
        max_turns=int(run.budget.get("model_turns", 12)),
        max_tool_calls=int(run.budget.get("tool_calls", 40)),
        max_usd=float(run.budget.get("usd", 3.0)),
    )
    started = perf_counter()
    try:
        artifact = run_scout(gateway, run.id, run.pinned_sha, run.task_text, model_id, budget)
    except ValueError as error:
        transition_run(
            session, run, RunStatus.REFUSED, "invalid_model_output", "worker", {"error": str(error)}
        )
        return
    sequence = (
        session.scalar(select(func.count(ModelCall.id)).where(ModelCall.run_id == run.id)) or 0
    ) + 1
    session.add(
        ModelCall(
            run_id=run.id,
            sequence=sequence,
            model_id=model_id,
            provider="configured_gateway",
            settings={"data_collection": "deny", "fallback": False},
            usage={},
            billed_cost=0.0,
            latency_ms=int((perf_counter() - started) * 1000),
            langfuse_trace_id=str(run.id),
        )
    )
    transition_run(session, run, RunStatus.EVALUATING, "scout_output_validated", "worker")
    store_artifact(session, artifact, "scout")
    transition_run(session, run, RunStatus.SUCCEEDED, "scout_artifact_stored", "worker")


def orchestrate_assessor(session: Session, run: Run, gateway: ModelGateway, model_id: str) -> None:
    if run.role is not AgentRole.ASSESSOR or run.status is not RunStatus.LEASED:
        raise ValueError("only leased assessor runs can be orchestrated")
    transition_run(session, run, RunStatus.SNAPSHOTTING, "diff_policy_checked", "worker")
    transition_run(session, run, RunStatus.RUNNING, "assessor_started", "worker")
    budget = ModelBudget(
        int(run.budget.get("model_turns", 12)),
        int(run.budget.get("tool_calls", 40)),
        float(run.budget.get("usd", 3)),
    )
    try:
        artifact = run_assessor(gateway, run.id, run.pinned_sha, run.task_text, model_id, budget)
    except ValueError as error:
        transition_run(
            session, run, RunStatus.REFUSED, "invalid_risk_output", "worker", {"error": str(error)}
        )
        return
    transition_run(session, run, RunStatus.EVALUATING, "risk_output_validated", "worker")
    store_artifact(session, artifact, "risk")
    transition_run(session, run, RunStatus.SUCCEEDED, "risk_artifact_stored", "worker")
