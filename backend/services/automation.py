import asyncio
import json
from datetime import timedelta

from sqlalchemy import select

from backend.core.policy import RiskLevel, evaluate_action
from backend.database import SessionLocal
from backend.models.entities import (
    Approval,
    ApprovalContext,
    AuditLog,
    Automation,
    Task,
    ToolCall,
    now_utc,
)
from backend.security.audit import append_security_event
from backend.security.emergency import emergency_active
from backend.services.execution import execute_tool_call
from backend.services.tools import TOOL_RISKS


def run_due_automations() -> int:
    db = SessionLocal()
    executed = 0
    try:
        current = now_utc()
        due = db.scalars(
            select(Automation).where(
                Automation.enabled.is_(True), Automation.next_run <= current
            )
        ).all()
        for automation in due:
            risk = RiskLevel(TOOL_RISKS[automation.action])
            decision = evaluate_action(
                automation.action, risk, "admin", emergency_active(db)
            )
            if not decision.allowed:
                automation.last_run = current
                automation.next_run = current + timedelta(minutes=automation.interval_minutes)
                append_security_event(
                    db, "automation.run", "denied", f"automation={automation.id}"
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
                        requested_by="automation",
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
