import json
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.policy import RiskLevel, evaluate_action
from backend.database import get_db
from backend.models.entities import AuditLog, Automation, now_utc
from backend.models.schemas import AutomationCreate, AutomationRead
from backend.security.audit import append_security_event
from backend.security.dependencies import OperatorDependency, PrincipalDependency
from backend.security.emergency import emergency_active
from backend.services.tools import SUPPORTED_TOOLS, TOOL_RISKS

router = APIRouter(prefix="/automations", tags=["automations"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AutomationRead])
def list_automations(db: Database) -> list[Automation]:
    return list(db.scalars(select(Automation).order_by(Automation.created_at.desc())).all())


@router.post("", response_model=AutomationRead, status_code=201)
def create_automation(
    payload: AutomationCreate, principal: PrincipalDependency, db: Database
) -> Automation:
    if payload.action not in SUPPORTED_TOOLS:
        raise HTTPException(status_code=422, detail="Unsupported automation tool.")
    decision = evaluate_action(
        payload.action,
        RiskLevel(TOOL_RISKS[payload.action]),
        principal.role,
        emergency_active(db),
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)
    automation = Automation(
        title=payload.title,
        action=payload.action,
        arguments=json.dumps(payload.arguments),
        interval_minutes=payload.interval_minutes,
        next_run=now_utc() + timedelta(minutes=payload.interval_minutes),
        owner_id=principal.user_id,
        owner_role=principal.role,
    )
    db.add(automation)
    db.add(AuditLog(action="automation.create", outcome="success", detail=payload.action))
    append_security_event(
        db, "automation.create", "success", f"action={payload.action}", principal.user_id
    )
    db.commit()
    db.refresh(automation)
    return automation


@router.post("/{automation_id}/enabled/{enabled}", response_model=AutomationRead)
def set_automation_enabled(
    automation_id: str, enabled: bool, principal: OperatorDependency, db: Database
) -> Automation:
    automation = db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    if enabled:
        decision = evaluate_action(
            automation.action,
            RiskLevel(TOOL_RISKS.get(automation.action, RiskLevel.SENSITIVE)),
            principal.role,
            emergency_active(db),
        )
        if not decision.allowed:
            raise HTTPException(status_code=403, detail=decision.reason)
    automation.enabled = enabled
    if enabled:
        automation.next_run = now_utc() + timedelta(minutes=automation.interval_minutes)
    db.add(AuditLog(action="automation.toggle", outcome=str(enabled).lower(), detail=automation_id))
    db.commit()
    db.refresh(automation)
    return automation


@router.delete("/{automation_id}", status_code=204)
def delete_automation(automation_id: str, _: OperatorDependency, db: Database) -> Response:
    automation = db.get(Automation, automation_id)
    if automation is None:
        raise HTTPException(status_code=404, detail="Automation not found")
    db.delete(automation)
    db.add(AuditLog(action="automation.delete", outcome="success", detail=automation_id))
    db.commit()
    return Response(status_code=204)
