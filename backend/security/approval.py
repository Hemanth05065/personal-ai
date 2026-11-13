import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from backend.models.entities import Approval, ApprovalGrant, ToolCall, now_utc
from backend.security.audit import append_security_event


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
    expires = grant.expires_at.replace(tzinfo=UTC) if grant.expires_at.tzinfo is None else grant.expires_at
    if expires <= datetime.now(UTC):
        return False
    expected = action_fingerprint(approval.task_id, call)
    if not hmac.compare_digest(expected, grant.action_hash):
        append_security_event(db, "approval.consume", "tamper_detected", f"approval={approval.id}")
        return False
    grant.used_at = now_utc()
    append_security_event(db, "approval.consume", "success", f"approval={approval.id}", grant.approved_by)
    db.flush()
    return True
