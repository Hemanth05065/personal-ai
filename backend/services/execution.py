import json

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import Approval, AuditLog, Task, ToolCall, now_utc
from backend.security.approval import consume_approval
from backend.security.audit import append_security_event
from backend.security.emergency import emergency_active
from backend.services.tools import ToolError, execute_tool
from backend.services.versions import capture_before_write, record_written


def execute_tool_call(
    db: Session, task: Task, call: ToolCall, approval: Approval | None = None
) -> ToolCall:
    if emergency_active(db):
        call.status = "cancelled"
        task.status = "cancelled"
        call.result = json.dumps({"error": "Emergency stop is active."})
        call.finished_at = now_utc()
        append_security_event(db, "tool.execute", "denied", "Emergency stop active")
        db.commit()
        return call
    if approval is not None and not consume_approval(db, approval, call):
        call.status = "failed"
        task.status = "failed"
        call.result = json.dumps({"error": "Approval is invalid, expired, used, or mismatched."})
        call.finished_at = now_utc()
        append_security_event(db, "tool.execute", "denied", "Approval revalidation failed")
        db.commit()
        return call
    call.status = "running"
    task.status = "running"
    # Every write keeps the file's previous version so it can be undone.
    version = capture_before_write(db, call, get_settings()) if call.tool_name == "write_file" else None
    db.commit()
    try:
        result = execute_tool(call.tool_name, json.loads(call.arguments), get_settings())
        call.result = result.serialize()
        call.status = "completed"
        task.status = "completed"
        outcome = "success"
    except (ToolError, ValueError, TypeError) as exc:
        call.result = json.dumps({"error": str(exc)})
        call.status = "failed"
        task.status = "failed"
        outcome = "failed"
    call.finished_at = now_utc()
    record_written(version, call)
    db.add(AuditLog(action=f"tool.{call.tool_name}", outcome=outcome, detail=call.id))
    append_security_event(db, f"tool.{call.tool_name}", outcome, f"call={call.id}")
    db.commit()
    db.refresh(call)
    return call
