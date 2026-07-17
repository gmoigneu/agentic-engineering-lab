from __future__ import annotations

import hashlib
import json
from time import perf_counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentic_lab.agents.assessor import ASSESSOR_SYSTEM_PROMPT, run_assessor
from agentic_lab.agents.ci import (
    CI_SYSTEM_PROMPT,
    build_refusal,
    classify_failure,
    requires_refusal,
    run_ci_diagnosis,
)
from agentic_lab.agents.scout import SCOUT_SYSTEM_PROMPT, run_scout
from agentic_lab.db.models import ModelCall, RedactionEvent, Run, ToolCall
from agentic_lab.domain.enums import AgentRole, RunStatus
from agentic_lab.domain.schemas import TerminalError
from agentic_lab.gateway.capability import CapabilityGateway
from agentic_lab.gateway.model import (
    BudgetExhaustedError,
    ModelBudget,
    ModelGateway,
    ModelGatewayError,
)
from agentic_lab.gateway.redaction import redact
from agentic_lab.policy.audit import DatabaseCapabilityAudit
from agentic_lab.runs.artifacts import store_artifact
from agentic_lab.runs.service import transition_run
from agentic_lab.tools.registry import SnapshotToolRegistry


def orchestrate_scout(
    session: Session,
    run: Run,
    gateway: ModelGateway,
    model_id: str,
    capability_gateway: CapabilityGateway | None = None,
) -> None:
    if run.role is not AgentRole.SCOUT or run.status is not RunStatus.LEASED:
        raise ValueError("only leased Scout runs can be orchestrated")
    _pin_model_configuration(run, SCOUT_SYSTEM_PROMPT, model_id, run.evaluation_case_id is not None)
    transition_run(session, run, RunStatus.SNAPSHOTTING, "snapshot_policy_checked", "worker")
    tools = None
    if capability_gateway is not None:
        if capability_gateway.audit_port is None:
            capability_gateway = CapabilityGateway(
                capability_gateway.read_port,
                capability_gateway.allowed_repository_ids,
                DatabaseCapabilityAudit(session),
            )
        try:
            snapshot = capability_gateway.fetch_snapshot(
                str(run.id), run.role, run.repository_id, run.pinned_sha
            )
        except (FileNotFoundError, PermissionError, ValueError):
            transition_run(session, run, RunStatus.REFUSED, "snapshot_unavailable", "worker")
            return
        tools = SnapshotToolRegistry(run.role, snapshot, int(run.budget.get("tool_calls", 40)))
    transition_run(session, run, RunStatus.RUNNING, "scout_started", "worker")
    budget = ModelBudget(
        max_turns=int(run.budget.get("model_turns", 12)),
        max_tool_calls=int(run.budget.get("tool_calls", 40)),
        max_usd=float(run.budget.get("usd", 3.0)),
        max_wall_seconds=int(run.budget.get("wall_seconds", 1_200)),
    )
    started = perf_counter()
    try:
        artifact = run_scout(
            gateway,
            run.id,
            run.pinned_sha,
            run.task_text,
            model_id,
            budget,
            tools,
            run.evaluation_case_id is not None,
        )
    except BudgetExhaustedError as error:
        _record_terminal_error(
            session, run, "budget_exhausted", str(error), RunStatus.BUDGET_EXHAUSTED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ModelGatewayError as error:
        _record_terminal_error(session, run, "model_gateway_failure", str(error), RunStatus.FAILED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ValueError as error:
        _record_terminal_error(session, run, "invalid_model_output", str(error), RunStatus.REFUSED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except Exception as error:
        _record_terminal_error(
            session, run, "model_gateway_failure", type(error).__name__, RunStatus.FAILED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    _record_model_call(session, run, gateway, model_id, started)
    _record_tool_calls(session, run, tools)
    transition_run(session, run, RunStatus.EVALUATING, "scout_output_validated", "worker")
    record = store_artifact(session, artifact, "scout")
    if record.redaction_state == "blocked":
        transition_run(session, run, RunStatus.REFUSED, "artifact_secret_detection", "worker")
        return
    transition_run(session, run, RunStatus.SUCCEEDED, "scout_artifact_stored", "worker")


def orchestrate_assessor(
    session: Session,
    run: Run,
    gateway: ModelGateway,
    model_id: str,
    capability_gateway: CapabilityGateway | None = None,
) -> None:
    if run.role is not AgentRole.ASSESSOR or run.status is not RunStatus.LEASED:
        raise ValueError("only leased assessor runs can be orchestrated")
    _pin_model_configuration(
        run, ASSESSOR_SYSTEM_PROMPT, model_id, run.evaluation_case_id is not None
    )
    transition_run(session, run, RunStatus.SNAPSHOTTING, "diff_policy_checked", "worker")
    tools = _snapshot_tools(session, run, capability_gateway)
    if capability_gateway is not None and tools is None:
        transition_run(session, run, RunStatus.REFUSED, "snapshot_unavailable", "worker")
        return
    transition_run(session, run, RunStatus.RUNNING, "assessor_started", "worker")
    budget = ModelBudget(
        int(run.budget.get("model_turns", 12)),
        int(run.budget.get("tool_calls", 40)),
        float(run.budget.get("usd", 3)),
        int(run.budget.get("wall_seconds", 1_200)),
    )
    started = perf_counter()
    try:
        artifact = run_assessor(
            gateway,
            run.id,
            run.pinned_sha,
            run.task_text,
            model_id,
            budget,
            tools,
            evaluation=run.evaluation_case_id is not None,
        )
    except BudgetExhaustedError as error:
        _record_terminal_error(
            session, run, "budget_exhausted", str(error), RunStatus.BUDGET_EXHAUSTED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ModelGatewayError as error:
        _record_terminal_error(session, run, "model_gateway_failure", str(error), RunStatus.FAILED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ValueError as error:
        _record_terminal_error(session, run, "invalid_risk_output", str(error), RunStatus.REFUSED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except Exception as error:
        _record_terminal_error(
            session, run, "model_gateway_failure", type(error).__name__, RunStatus.FAILED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    _record_model_call(session, run, gateway, model_id, started)
    _record_tool_calls(session, run, tools)
    transition_run(session, run, RunStatus.EVALUATING, "risk_output_validated", "worker")
    record = store_artifact(session, artifact, "risk")
    if record.redaction_state == "blocked":
        transition_run(session, run, RunStatus.REFUSED, "artifact_secret_detection", "worker")
        return
    transition_run(session, run, RunStatus.SUCCEEDED, "risk_artifact_stored", "worker")


def refuse_ci_failure(session: Session, run: Run, redacted_log: str) -> None:
    if run.role is not AgentRole.CI or run.status is not RunStatus.LEASED:
        raise ValueError("only leased CI runs can be diagnosed")
    transition_run(session, run, RunStatus.SNAPSHOTTING, "check_log_loaded", "worker")
    failure_class = classify_failure(redacted_log)
    if failure_class != "repository":
        transition_run(session, run, RunStatus.REFUSED, f"ci_{failure_class}_failure", "worker")
    else:
        transition_run(session, run, RunStatus.RUNNING, "ci_repository_failure", "worker")


def orchestrate_ci(
    session: Session,
    run: Run,
    gateway: ModelGateway,
    model_id: str,
    capability_gateway: CapabilityGateway | None = None,
) -> None:
    if run.role is not AgentRole.CI or run.status is not RunStatus.LEASED:
        raise ValueError("only leased CI runs can be orchestrated")
    _pin_model_configuration(run, CI_SYSTEM_PROMPT, model_id, run.evaluation_case_id is not None)
    transition_run(session, run, RunStatus.SNAPSHOTTING, "check_evidence_policy_checked", "worker")
    tools = _snapshot_tools(session, run, capability_gateway)
    if capability_gateway is not None and tools is None:
        transition_run(session, run, RunStatus.REFUSED, "snapshot_unavailable", "worker")
        return
    transition_run(session, run, RunStatus.RUNNING, "ci_diagnosis_started", "worker")
    budget = _budget(run)
    started = perf_counter()
    try:
        artifact = run_ci_diagnosis(
            gateway,
            run.id,
            run.pinned_sha,
            run.task_text,
            model_id,
            budget,
            tools,
            evaluation=run.evaluation_case_id is not None,
        )
    except BudgetExhaustedError as error:
        _record_terminal_error(
            session, run, "budget_exhausted", str(error), RunStatus.BUDGET_EXHAUSTED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ModelGatewayError as error:
        _record_terminal_error(session, run, "model_gateway_failure", str(error), RunStatus.FAILED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except ValueError as error:
        _record_terminal_error(session, run, "invalid_ci_output", str(error), RunStatus.REFUSED)
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    except Exception as error:
        _record_terminal_error(
            session, run, "model_gateway_failure", type(error).__name__, RunStatus.FAILED
        )
        _record_model_call(session, run, gateway, model_id, started)
        _record_tool_calls(session, run, tools)
        return
    _record_model_call(session, run, gateway, model_id, started)
    _record_tool_calls(session, run, tools)
    transition_run(session, run, RunStatus.EVALUATING, "ci_diagnosis_validated", "worker")
    record = store_artifact(session, artifact, "ci_diagnosis")
    if record.redaction_state == "blocked":
        transition_run(session, run, RunStatus.REFUSED, "artifact_secret_detection", "worker")
        return
    if requires_refusal(artifact):
        refusal = build_refusal(
            artifact,
            "failure is not safely attributable to repository source",
            "resolve the external precondition and rerun the check",
        )
        store_artifact(session, refusal, "refusal")
        transition_run(
            session, run, RunStatus.REFUSED, f"ci_{artifact.failure_class}_failure", "worker"
        )
        return
    if artifact.patch_proposed:
        transition_run(
            session,
            run,
            RunStatus.REFUSED,
            "ci_patch_requires_deterministic_executor_evidence",
            "worker",
        )
        return
    transition_run(session, run, RunStatus.SUCCEEDED, "ci_diagnosis_stored", "worker")


def _budget(run: Run) -> ModelBudget:
    return ModelBudget(
        int(run.budget.get("model_turns", 12)),
        int(run.budget.get("tool_calls", 40)),
        float(run.budget.get("usd", 3)),
        int(run.budget.get("wall_seconds", 1_200)),
    )


def _record_model_call(
    session: Session, run: Run, gateway: ModelGateway, model_id: str, started: float
) -> None:
    sequence = (
        session.scalar(select(func.count(ModelCall.id)).where(ModelCall.run_id == run.id)) or 0
    ) + 1
    metadata = getattr(gateway, "last_call", None)
    request = getattr(gateway, "last_request", None)
    provider_allowlist = tuple(
        getattr(
            gateway,
            "last_provider_allowlist",
            getattr(request, "provider_allowlist", ()),
        )
    )
    provider = getattr(metadata, "provider", "configured_gateway")
    usage = getattr(metadata, "usage", {})
    billed_cost = getattr(metadata, "billed_cost", 0.0)
    latency_ms = int((perf_counter() - started) * 1000)
    settings = {
        "data_collection": "deny",
        "fallback": bool(
            request is not None and not request.evaluation and len(provider_allowlist) != 1
        ),
        "prompt_hash": getattr(request, "prompt_hash", run.prompt_hash),
        "tool_definitions_hash": getattr(request, "tool_definitions_hash", None),
        "provider_allowlist": list(provider_allowlist),
    }
    trace_id = None
    trace_exporter = getattr(gateway, "trace_exporter", None)
    if trace_exporter is not None:
        trace_payload = json.dumps(
            {
                "run_id": str(run.id),
                "role": run.role.value,
                "pinned_sha": run.pinned_sha,
                "model_id": model_id,
                "provider": provider,
                "settings": settings,
                "usage": usage,
                "billed_cost": billed_cost,
                "latency_ms": latency_ms,
            },
            sort_keys=True,
        )
        try:
            export = trace_exporter.export(str(run.id), "model-call", trace_payload)
        except Exception:
            settings["trace_export"] = "failed"
        else:
            trace_id = export.trace_id
            settings["trace_export"] = "blocked" if export.detector_names else "exported"
            for detector_name in export.detector_names:
                session.add(
                    RedactionEvent(
                        run_id=run.id,
                        detector_name=detector_name,
                        content_hash=export.content_hash,
                        source_locator="trace:model-call",
                        resolution_state="blocked",
                    )
                )
    session.add(
        ModelCall(
            run_id=run.id,
            sequence=sequence,
            model_id=model_id,
            provider=provider,
            settings=settings,
            usage=usage,
            billed_cost=billed_cost,
            latency_ms=latency_ms,
            langfuse_trace_id=trace_id,
        )
    )


def _record_terminal_error(
    session: Session, run: Run, code: str, message: str, status: RunStatus
) -> None:
    redaction = redact(message[:1_000])
    safe_message = (
        "error detail blocked by redaction policy" if redaction.detected else redaction.text
    )
    error = TerminalError(
        run_id=run.id,
        role=run.role,
        pinned_sha=run.pinned_sha,
        code=code,
        message=safe_message,
        next_action="inspect the run evidence and correct the failed precondition",
    )
    store_artifact(session, error, "terminal_error")
    transition_run(session, run, status, code, "worker")


def _record_tool_calls(session: Session, run: Run, tools: SnapshotToolRegistry | None) -> None:
    if tools is None:
        return
    for record in tools.records:
        session.add(
            ToolCall(
                run_id=run.id,
                sequence=record.sequence,
                tool_name=record.tool_name,
                request_json=record.request,
                result_summary=record.result_summary,
                status=record.status,
                duration_ms=record.duration_ms,
            )
        )


def _snapshot_tools(
    session: Session,
    run: Run,
    capability_gateway: CapabilityGateway | None,
) -> SnapshotToolRegistry | None:
    if capability_gateway is None:
        return None
    gateway = capability_gateway
    if gateway.audit_port is None:
        gateway = CapabilityGateway(
            gateway.read_port,
            gateway.allowed_repository_ids,
            DatabaseCapabilityAudit(session),
        )
    try:
        snapshot = gateway.fetch_snapshot(str(run.id), run.role, run.repository_id, run.pinned_sha)
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    diff_evidence = None
    check_evidence = None
    try:
        if run.pull_number is not None:
            diff_evidence = gateway.fetch_pull_request_diff(
                str(run.id),
                run.role,
                run.repository_id,
                run.pull_number,
                run.pinned_sha,
            )
        if run.role is AgentRole.CI and run.check_run_id is not None:
            check_evidence = gateway.fetch_check_evidence(
                str(run.id),
                run.role,
                run.repository_id,
                run.check_run_id,
                run.pinned_sha,
            )
    except (FileNotFoundError, PermissionError, ValueError):
        return None
    return SnapshotToolRegistry(
        run.role,
        snapshot,
        int(run.budget.get("tool_calls", 40)),
        diff_evidence=diff_evidence,
        check_evidence=check_evidence,
    )


def _pin_model_configuration(run: Run, system_prompt: str, model_id: str, evaluation: bool) -> None:
    run.prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
    run.model_config = {
        "model_id": model_id,
        "data_collection": "deny",
        "evaluation": evaluation,
    }
