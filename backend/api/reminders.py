from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.entities import AuditLog, Reminder
from backend.security.auth import Principal
from backend.security.dependencies import PrincipalDependency
from backend.services.reminders import aware, fire_due_reminders

router = APIRouter(prefix="/reminders", tags=["reminders"])
Database = Annotated[Session, Depends(get_db)]

# Fired and dismissed reminders stay visible for a while, then drop out of the list.
RECENT_DAYS = 7


class ReminderCreate(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    due_at: datetime

    @field_validator("due_at")
    @classmethod
    def needs_time_zone(cls, value: datetime) -> datetime:
        # The browser sends UTC ("...Z"). A time without a zone would be ambiguous.
        if value.tzinfo is None:
            raise ValueError("due_at must include a time zone, e.g. 2026-11-20T09:30:00Z")
        return value.astimezone(UTC)


class ReminderRead(BaseModel):
    id: str
    text: str
    due_at: datetime
    status: str
    fired_at: datetime | None
    created_at: datetime

    @classmethod
    def of(cls, item: Reminder) -> "ReminderRead":
        return cls(
            id=item.id, text=item.text, due_at=aware(item.due_at), status=item.status,
            fired_at=aware(item.fired_at) if item.fired_at else None, created_at=aware(item.created_at),
        )


def _own(db: Session, principal: Principal, reminder_id: str) -> Reminder:
    reminder = db.get(Reminder, reminder_id)
    # Someone else's reminder looks the same as a missing one.
    if reminder is None or reminder.owner_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder


@router.get("", response_model=list[ReminderRead])
def list_reminders(principal: PrincipalDependency, db: Database) -> list[ReminderRead]:
    """Your pending reminders, plus fired and dismissed ones from the last week."""
    fire_due_reminders(db, principal.user_id)
    cutoff = datetime.now(UTC) - timedelta(days=RECENT_DAYS)
    items = db.scalars(
        select(Reminder).where(Reminder.owner_id == principal.user_id).order_by(Reminder.due_at)
    ).all()
    return [
        ReminderRead.of(item) for item in items
        if item.status in {"pending", "fired"} or aware(item.due_at) >= cutoff
    ]


@router.post("", response_model=ReminderRead, status_code=201)
def create_reminder(payload: ReminderCreate, principal: PrincipalDependency, db: Database) -> ReminderRead:
    reminder = Reminder(owner_id=principal.user_id, text=payload.text.strip(), due_at=payload.due_at)
    db.add(reminder)
    db.add(AuditLog(action="reminder.create", outcome="success", detail=reminder.id))
    db.commit()
    db.refresh(reminder)
    return ReminderRead.of(reminder)


@router.post("/{reminder_id}/dismiss", response_model=ReminderRead)
def dismiss_reminder(reminder_id: str, principal: PrincipalDependency, db: Database) -> ReminderRead:
    reminder = _own(db, principal, reminder_id)
    if reminder.status != "fired":
        raise HTTPException(status_code=409, detail="Only a reminder that has gone off can be dismissed")
    reminder.status = "dismissed"
    db.commit()
    return ReminderRead.of(reminder)


@router.delete("/{reminder_id}", status_code=204)
def cancel_reminder(reminder_id: str, principal: PrincipalDependency, db: Database) -> Response:
    reminder = _own(db, principal, reminder_id)
    if reminder.status != "pending":
        raise HTTPException(status_code=409, detail="Only an upcoming reminder can be cancelled")
    reminder.status = "cancelled"
    db.add(AuditLog(action="reminder.cancel", outcome="success", detail=reminder.id))
    db.commit()
    return Response(status_code=204)
