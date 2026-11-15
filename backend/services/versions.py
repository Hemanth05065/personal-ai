"""Keep the previous version of every file the assistant writes, so any write can be undone.

Undo is deliberately careful: it only restores if the file still holds exactly
what the assistant wrote. If you (or anything else) changed the file since,
undo refuses rather than throwing away the newer content.
"""

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.models.entities import AuditLog, FileVersion, ToolCall, now_utc
from backend.security.audit import append_security_event
from backend.services.tools import ToolError, resolve_workspace_path

KEEP_VERSIONS_FOR = timedelta(days=30)


class UndoRefused(Exception):
    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code = status_code
        self.reason = reason


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def capture_before_write(db: Session, call: ToolCall, settings: Settings) -> FileVersion | None:
    """Record the file's current state before a write_file call runs."""
    path = str(json.loads(call.arguments or "{}").get("path", ""))
    try:
        target = resolve_workspace_path(settings, path)
    except ToolError:
        return None  # the write itself will fail with the same error
    existed = target.is_file()
    previous = None
    if existed and target.stat().st_size <= settings.max_file_bytes:
        previous = target.read_bytes()
    version = FileVersion(call_id=call.id, path=path, existed=existed, previous=previous)
    db.add(version)
    cutoff = datetime.now(UTC) - KEEP_VERSIONS_FOR
    db.execute(delete(FileVersion).where(FileVersion.created_at < cutoff))
    return version


def record_written(version: FileVersion | None, call: ToolCall) -> None:
    if version is None or call.status != "completed":
        return
    content = str(json.loads(call.arguments or "{}").get("content", ""))
    version.written_hash = _digest(content.encode("utf-8"))


def undo_write(db: Session, call_id: str, settings: Settings, actor_id: str) -> str:
    """Restore the file to how it was before the write. Returns what was done, in words."""
    version = db.scalar(select(FileVersion).where(FileVersion.call_id == call_id))
    if version is None:
        raise UndoRefused(404, "There is no saved version for this action.")
    if version.undone_at is not None:
        raise UndoRefused(409, "This change was already undone.")
    if version.written_hash is None:
        raise UndoRefused(409, "The write didn’t complete, so there is nothing to undo.")
    target = resolve_workspace_path(settings, version.path)
    current = target.read_bytes() if target.is_file() else None
    if current is None or _digest(current) != version.written_hash:
        raise UndoRefused(409, f"{version.path} was changed after this write, so undo would lose newer content.")
    if version.existed:
        if version.previous is None:
            raise UndoRefused(409, "The previous version was too large to keep, so this can’t be undone.")
        target.write_bytes(version.previous)
        summary = f"Restored the previous version of {version.path}."
    else:
        target.unlink()
        summary = f"Removed {version.path}, which this action had created."
    version.undone_at = now_utc()
    db.add(AuditLog(action="file.undo", outcome="success", detail=call_id))
    append_security_event(db, "file.undo", "success", f"call={call_id}; path={version.path}", actor_id)
    db.commit()
    return summary
