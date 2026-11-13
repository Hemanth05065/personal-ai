from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.entities import Reminder, now_utc


def aware(value: datetime) -> datetime:
    """SQLite drops time zones; every stored time here is UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def fire_due_reminders(db: Session, owner_id: str | None = None) -> int:
    """Mark pending reminders whose time has come as fired. Returns how many fired."""
    query = select(Reminder).where(Reminder.status == "pending")
    if owner_id is not None:
        query = query.where(Reminder.owner_id == owner_id)
    current = now_utc()
    due = [item for item in db.scalars(query).all() if aware(item.due_at) <= current]
    for reminder in due:
        reminder.status = "fired"
        reminder.fired_at = current
    if due:
        db.commit()
    return len(due)
