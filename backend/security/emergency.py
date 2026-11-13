from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.models.entities import (
    Approval,
    ApprovalGrant,
    SecurityState,
    Task,
    ToolCall,
    now_utc,
)
from backend.security.audit import append_security_event


def get_security_state(db: Session) -> SecurityState:
    state = db.get(SecurityState, 1)
    if state is None:
        state = SecurityState(id=1)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


def emergency_active(db: Session) -> bool:
    return get_security_state(db).emergency_stopped


def activate_emergency_stop(db: Session, reason: str, actor_id: str) -> SecurityState:
    state = get_security_state(db)
    state.emergency_stopped = True
    state.reason = reason
    state.activated_at = now_utc()
    state.activated_by = actor_id
    db.execute(
        update(Task)
        .where(Task.status.in_(["planned", "running", "awaiting_approval"]))
        .values(status="cancelled")
    )
    db.execute(
        update(ToolCall)
        .where(ToolCall.status.in_(["pending", "running", "awaiting_approval"]))
        .values(status="cancelled", finished_at=now_utc())
    )
    db.execute(update(Approval).where(Approval.status == "pending").values(status="denied"))
    db.execute(
        update(ApprovalGrant)
        .where(ApprovalGrant.used_at.is_(None))
        .values(used_at=now_utc())
    )
    append_security_event(db, "emergency_stop", "activated", reason, actor_id)
    db.commit()
    db.refresh(state)
    return state


def resume_operations(db: Session, actor_id: str) -> SecurityState:
    state = get_security_state(db)
    state.emergency_stopped = False
    state.reason = ""
    state.activated_at = None
    state.activated_by = None
    append_security_event(db, "emergency_stop", "resumed", "Explicit admin resume", actor_id)
    db.commit()
    db.refresh(state)
    return state
