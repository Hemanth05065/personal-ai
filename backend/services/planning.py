"""One path for turning a requested action into a task.

Used by the Tasks API (actions the user plans by hand) and by chat (actions the
model proposes), so both go through the same policy, role limits, approval gate
and audit trail. The model never gets a route around this.
"""

import json
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.policy import RiskLevel, evaluate_action
from backend.models.entities import Approval, ApprovalContext, AuditLog, Task, ToolCall
from backend.security.approval import grant_approval
from backend.security.audit import append_security_event
from backend.security.auth import Principal
from backend.security.emergency import emergency_active
from backend.services.execution import execute_tool_call
from backend.services.tools import SUPPORTED_TOOLS, TOOL_RISKS


class PlanRejected(Exception):
    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


@dataclass
class PlannedTask:
    task: Task
    call: ToolCall
    approval: Approval | None

    @property
    def needs_approval(self) -> bool:
        return self.approval is not None


def plan_task(
    db: Session,
    principal: Principal,
    *,
    title: str,
    description: str,
    action: str,
    arguments: dict,
    requested_risk: int = 0,
    proposed_by_assistant: bool = False,
) -> PlannedTask:
    """Create a task. Runs it now if policy allows; otherwise leaves it awaiting approval.

    Raises PlanRejected when the action is denied or unsupported.
    """
    decision = evaluate_action(action, RiskLevel(requested_risk), principal.role, emergency_active(db))
    if not decision.allowed:
        raise PlanRejected(403, decision.reason)
    if action not in SUPPORTED_TOOLS:
        raise PlanRejected(422, "This tool is not available in the local MVP.")
    # The server decides the real risk; a client (or model) claiming less is ignored.
    effective_risk = RiskLevel(max(requested_risk, TOOL_RISKS[action]))
    decision = evaluate_action(action, effective_risk, principal.role, emergency_active(db))
    if not decision.allowed:
        append_security_event(db, "permission.task", "denied", decision.reason, principal.user_id)
        db.commit()
        raise PlanRejected(403, decision.reason)

    status = "awaiting_approval" if decision.approval_required else "planned"
    task = Task(title=title, description=description, risk_level=int(effective_risk), status=status)
    db.add(task)
    db.flush()
    call = ToolCall(
        task_id=task.id,
        tool_name=action,
        arguments=json.dumps(arguments),
        status="awaiting_approval" if decision.approval_required else "pending",
    )
    db.add(call)
    db.flush()
    approval = None
    if decision.approval_required:
        approval = Approval(task_id=task.id, action=action, reason=decision.reason)
        db.add(approval)
        db.flush()
        targets = [str(arguments.get("path", "workspace"))]
        summary = description or title
        db.add(
            ApprovalContext(
                approval_id=approval.id,
                description=f"Proposed by the assistant in chat: {summary}" if proposed_by_assistant else summary,
                justification=decision.reason,
                targets=json.dumps(targets),
                consequences=(
                    "This action can change data in the authorized workspace. "
                    "Approval is bound to the exact tool name and arguments and expires in 10 minutes."
                ),
                requested_by=principal.user_id,
            )
        )
    origin = "assistant" if proposed_by_assistant else "user"
    db.add(AuditLog(action="task.create", outcome=status, detail=f"{action}; origin={origin}"))
    append_security_event(
        db,
        "permission.task",
        "approval_required" if decision.approval_required else "allowed",
        f"action={action}; risk={int(effective_risk)}; origin={origin}",
        principal.user_id,
    )
    db.commit()
    db.refresh(task)
    if not decision.approval_required:
        execute_tool_call(db, task, call)
        db.refresh(task)
        db.refresh(call)
    return PlannedTask(task, call, approval)


def approve_and_run(db: Session, approval: Approval, principal: Principal, *, automatic: bool = False) -> ToolCall | None:
    """Approve a pending request and run it: the one path for the Approve button and Do-it mode.

    The approver's own role must allow the action's risk, the emergency stop
    applies, and the grant is bound to the exact tool and arguments. Raises
    PlanRejected if the approver may not run it.
    """
    task = db.get(Task, approval.task_id)
    allowed = evaluate_action(
        approval.action,
        RiskLevel(task.risk_level if task else RiskLevel.SENSITIVE),
        principal.role,
        emergency_active(db),
    )
    if not allowed.allowed:
        append_security_event(
            db, "approval.decide", "denied", f"approval={approval.id}; {allowed.reason}", principal.user_id
        )
        db.commit()
        raise PlanRejected(403, allowed.reason)
    outcome = "auto_approved" if automatic else "approved"
    approval.status = "approved"
    if task:
        task.status = "planned"
    call = db.scalar(select(ToolCall).where(ToolCall.task_id == approval.task_id))
    if call:
        call.status = "pending"
        grant_approval(db, approval, call, principal.user_id)
    db.add(AuditLog(action="approval.decide", outcome=outcome, detail=approval.id))
    detail = f"approval={approval.id}" + ("; do-it mode" if automatic else "")
    append_security_event(db, "approval.decide", outcome, detail, principal.user_id)
    db.commit()
    db.refresh(approval)
    if task and call:
        execute_tool_call(db, task, call, approval)
    return call
