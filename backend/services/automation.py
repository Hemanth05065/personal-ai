import asyncio
import json
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.policy import PolicyDecision, RiskLevel, evaluate_action
from backend.database import SessionLocal
from backend.models.entities import (
    Approval,
    ApprovalContext,
    AuditLog,
    Automation,
    Task,
    ToolCall,
    User,
    now_utc,
)
from backend.security.approval import expire_stale_approvals
from backend.security.audit import append_security_event
from backend.security.emergency import emergency_active
from backend.services.execution import execute_tool_call
from backend.services.tools import TOOL_RISKS

# Principals that have no row in the users table (API key, auth disabled in development).
SERVICE_PRINCIPALS = {"service", "local-development"}


def owner_role(db: Session, automation: Automation) -> str | None:
    """The role an automation runs with: its owner's current role, or None to deny.

    A downgraded owner's rules lose power on their next run; a disabled or deleted
    owner's rules stop running; rules created before ownership was recorded never
    run as an implicit admin.
    """
    if not automation.owner_id:
        return None
    user = db.get(User, automation.owner_id)
    if user is not None:
        return None if user.disabled else user.role
    if automation.owner_id in SERVICE_PRINCIPALS:
        return automation.owner_role
    return None


def run_due_automations() -> int:
    db = SessionLocal()
    executed = 0
    try:
        expire_stale_approvals(db)
        current = now_utc()
        due = db.scalars(
            select(Automation).where(
                Automation.enabled.is_(True), Automation.next_run <= current
            )
        ).all()
        for automation in due:
            risk = RiskLevel(TOOL_RISKS[automation.action])
            role = owner_role(db, automation)
            if role is None:
                decision = PolicyDecision(
                    False, False, "The automation has no active owner; recreate it to run it."
                )
            else:
                decision = evaluate_action(automation.action, risk, role, emergency_active(db))
            if not decision.allowed:
                automation.last_run = current
                automation.next_run = current + timedelta(minutes=automation.interval_minutes)
                append_security_event(
                    db,
                    "automation.run",
                    "denied",
                    f"automation={automation.id}; {decision.reason}",
                    automation.owner_id,
                )
                db.commit()
                continue
            task = Task(
                title=f"Scheduled: {automation.title}",
                description=f"Created by automation {automation.id}",
                status="awaiting_approval" if decision.approval_required else "planned",
                risk_level=int(risk),
            )
            db.add(task)
            db.flush()
            call = ToolCall(
                task_id=task.id,
                tool_name=automation.action,
                arguments=automation.arguments,
                status="awaiting_approval" if decision.approval_required else "pending",
            )
            db.add(call)
            db.flush()
            if decision.approval_required:
                approval = Approval(
                    task_id=task.id,
                    action=automation.action,
                    reason="Scheduled side effects require approval for every run.",
                )
                db.add(approval)
                db.flush()
                db.add(
                    ApprovalContext(
                        approval_id=approval.id,
                        description=f"Scheduled automation: {automation.title}",
                        justification=approval.reason,
                        targets=json.dumps(
                            [json.loads(automation.arguments).get("path", "workspace")]
                        ),
                        consequences="This scheduled action can change authorized workspace data.",
                        requested_by=automation.owner_id,
                    )
                )
            automation.last_run = current
            automation.next_run = current + timedelta(minutes=automation.interval_minutes)
            db.add(
                AuditLog(
                    action="automation.run",
                    outcome="awaiting_approval" if decision.approval_required else "started",
                    detail=automation.id,
                )
            )
            db.commit()
            if not decision.approval_required:
                execute_tool_call(db, task, call)
            executed += 1
        return executed
    finally:
        db.close()


async def automation_loop() -> None:
    while True:
        await asyncio.to_thread(run_due_automations)
        await asyncio.sleep(30)
