import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import Approval, ApprovalGrant, Task, ToolCall, now_utc
from backend.security.audit import append_security_event


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def expire_stale_approvals(db: Session) -> int:
    """Expire pending approvals older than the configured limit. Returns how many expired."""
    cutoff = datetime.now(UTC) - timedelta(hours=get_settings().approval_pending_hours)
    pending = db.scalars(select(Approval).where(Approval.status == "pending")).all()
    stale = [item for item in pending if _aware(item.created_at) <= cutoff]
    for approval in stale:
        approval.status = "expired"
        task = db.get(Task, approval.task_id)
        if task:
            task.status = "expired"
        for call in db.scalars(select(ToolCall).where(ToolCall.task_id == approval.task_id)).all():
            call.status = "cancelled"
        append_security_event(db, "approval.expire", "expired", f"approval={approval.id}")
    if stale:
        db.commit()
    return len(stale)


def action_fingerprint(task_id: str, call: ToolCall) -> str:
    canonical = json.dumps(
        {"task_id": task_id, "tool_name": call.tool_name, "arguments": json.loads(call.arguments)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def grant_approval(
    db: Session, approval: Approval, call: ToolCall, actor_id: str, ttl_minutes: int = 10
) -> ApprovalGrant:
    grant = ApprovalGrant(
        approval_id=approval.id,
        action_hash=action_fingerprint(approval.task_id, call),
        approved_by=actor_id,
        expires_at=now_utc() + timedelta(minutes=ttl_minutes),
    )
    db.add(grant)
    append_security_event(db, "approval.grant", "approved", f"approval={approval.id}", actor_id)
    db.flush()
    return grant


def consume_approval(db: Session, approval: Approval, call: ToolCall) -> bool:
    grant = db.query(ApprovalGrant).filter(ApprovalGrant.approval_id == approval.id).one_or_none()
    if grant is None or grant.used_at is not None:
        return False
    if _aware(grant.expires_at) <= datetime.now(UTC):
        return False
    expected = action_fingerprint(approval.task_id, call)
    if not hmac.compare_digest(expected, grant.action_hash):
        append_security_event(db, "approval.consume", "tamper_detected", f"approval={approval.id}")
        return False
    grant.used_at = now_utc()
    append_security_event(db, "approval.consume", "success", f"approval={approval.id}", grant.approved_by)
    db.flush()
    return True
