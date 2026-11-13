import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.policy import RiskLevel, evaluate_action
from backend.database import get_db
from backend.models.entities import Approval, ApprovalContext, AuditLog, Task, ToolCall
from backend.models.schemas import ApprovalDetail, TaskCreate, TaskRead, ToolCallRead
from backend.security.approval import grant_approval
from backend.security.audit import append_security_event
from backend.security.dependencies import PrincipalDependency
from backend.security.emergency import emergency_active
from backend.services.execution import execute_tool_call
from backend.services.tools import SUPPORTED_TOOLS, TOOL_RISKS

router = APIRouter(tags=["tasks"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/tasks", response_model=list[TaskRead])
def list_tasks(db: Database) -> list[Task]:
    return list(db.scalars(select(Task).order_by(Task.created_at.desc())).all())


@router.post("/tasks", response_model=TaskRead, status_code=201)
def create_task(payload: TaskCreate, principal: PrincipalDependency, db: Database) -> Task:
    requested_risk = RiskLevel(payload.risk_level)
    decision = evaluate_action(
        payload.action, requested_risk, principal.role, emergency_active(db)
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)
    if payload.action not in SUPPORTED_TOOLS:
        raise HTTPException(status_code=422, detail="This tool is not available in the local MVP.")
    effective_risk = RiskLevel(max(payload.risk_level, TOOL_RISKS[payload.action]))
    decision = evaluate_action(
        payload.action, effective_risk, principal.role, emergency_active(db)
    )
    if not decision.allowed:
        append_security_event(
            db, "permission.task", "denied", decision.reason, principal.user_id
        )
        db.commit()
        raise HTTPException(status_code=403, detail=decision.reason)
    status = "awaiting_approval" if decision.approval_required else "planned"
    task = Task(
        title=payload.title,
        description=payload.description,
        risk_level=int(effective_risk),
        status=status,
    )
    db.add(task)
    db.flush()
    call = ToolCall(
        task_id=task.id,
        tool_name=payload.action,
        arguments=json.dumps(payload.arguments),
        status="awaiting_approval" if decision.approval_required else "pending",
    )
    db.add(call)
    db.flush()
    if decision.approval_required:
        approval = Approval(task_id=task.id, action=payload.action, reason=decision.reason)
        db.add(approval)
        db.flush()
        targets = [str(payload.arguments.get("path", "workspace"))]
        db.add(
            ApprovalContext(
                approval_id=approval.id,
                description=payload.description or payload.title,
                justification=decision.reason,
                targets=json.dumps(targets),
                consequences=(
                    "This action can change data in the authorized workspace. "
                    "Approval is bound to the exact tool name and arguments and expires in 10 minutes."
                ),
                requested_by=principal.user_id,
            )
        )
    db.add(AuditLog(action="task.create", outcome=status, detail=payload.action))
    append_security_event(
        db,
        "permission.task",
        "approval_required" if decision.approval_required else "allowed",
        f"action={payload.action}; risk={int(effective_risk)}",
        principal.user_id,
    )
    db.commit()
    db.refresh(task)
    if not decision.approval_required:
        execute_tool_call(db, task, call)
        db.refresh(task)
    return task


@router.get("/approvals", response_model=list[ApprovalDetail])
def list_approvals(db: Database) -> list[ApprovalDetail]:
    items = db.scalars(select(Approval).order_by(Approval.created_at.desc())).all()
    result = []
    for approval in items:
        context = db.scalar(
            select(ApprovalContext).where(ApprovalContext.approval_id == approval.id)
        )
        result.append(
            ApprovalDetail(
                id=approval.id,
                task_id=approval.task_id,
                action=approval.action,
                status=approval.status,
                reason=approval.reason,
                created_at=approval.created_at,
                description=context.description if context else approval.action,
                justification=context.justification if context else approval.reason,
                targets=json.loads(context.targets) if context else [],
                consequences=context.consequences if context else "No context recorded.",
            )
        )
    return result


@router.get("/tasks/{task_id}/receipts", response_model=list[ToolCallRead])
def task_receipts(task_id: str, db: Database) -> list[ToolCall]:
    if db.get(Task, task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return list(
        db.scalars(
            select(ToolCall)
            .where(ToolCall.task_id == task_id)
            .order_by(ToolCall.created_at)
        ).all()
    )


@router.post("/approvals/{approval_id}/{decision}", response_model=ApprovalDetail)
def decide_approval(
    approval_id: str, decision: str, principal: PrincipalDependency, db: Database
):
    if decision not in {"approved", "denied"}:
        raise HTTPException(status_code=400, detail="Decision must be approved or denied")
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(status_code=404, detail="Approval not found")
    if approval.status != "pending":
        raise HTTPException(status_code=409, detail="Approval has already been decided")
    approval.status = decision
    task = db.get(Task, approval.task_id)
    if task:
        task.status = "planned" if decision == "approved" else "cancelled"
    call = db.scalar(select(ToolCall).where(ToolCall.task_id == approval.task_id))
    if call:
        call.status = "pending" if decision == "approved" else "cancelled"
    if decision == "approved" and call:
        grant_approval(db, approval, call, principal.user_id)
    db.add(AuditLog(action="approval.decide", outcome=decision, detail=approval.id))
    append_security_event(
        db, "approval.decide", decision, f"approval={approval.id}", principal.user_id
    )
    db.commit()
    db.refresh(approval)
    if decision == "approved" and task and call:
        execute_tool_call(db, task, call, approval)
    context = db.scalar(
        select(ApprovalContext).where(ApprovalContext.approval_id == approval.id)
    )
    return ApprovalDetail(
        id=approval.id,
        task_id=approval.task_id,
        action=approval.action,
        status=approval.status,
        reason=approval.reason,
        created_at=approval.created_at,
        description=context.description if context else approval.action,
        justification=context.justification if context else approval.reason,
        targets=json.loads(context.targets) if context else [],
        consequences=context.consequences if context else "No context recorded.",
    )
