import hashlib
import hmac
import json
import os
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models.entities import SecureAuditRecord, now_utc

REDACTIONS = [
    re.compile(r"(?i)(password|token|secret|authorization|cookie)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~-]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
]


def _key_path() -> Path:
    settings = get_settings()
    directory = settings.security_dir.resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory / "audit.key"


def _audit_key() -> bytes:
    path = _key_path()
    if not path.exists():
        path.write_bytes(secrets.token_bytes(32))
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path.read_bytes()


def redact(value: str) -> str:
    cleaned = value[:4_000]
    for pattern in REDACTIONS:
        cleaned = pattern.sub("[REDACTED]", cleaned)
    return cleaned


def _timestamp(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _digest(
    sequence: int,
    event_type: str,
    outcome: str,
    actor_id: str | None,
    detail: str,
    previous: str,
    timestamp: str,
) -> str:
    payload = json.dumps(
        {
            "sequence": sequence,
            "event_type": event_type,
            "outcome": outcome,
            "actor_id": actor_id,
            "detail": detail,
            "previous_hash": previous,
            "created_at": timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hmac.new(_audit_key(), payload, hashlib.sha256).hexdigest()


def append_security_event(
    db: Session,
    event_type: str,
    outcome: str,
    detail: str = "",
    actor_id: str | None = None,
) -> SecureAuditRecord:
    last = db.scalar(select(SecureAuditRecord).order_by(SecureAuditRecord.sequence.desc()).limit(1))
    sequence = (last.sequence + 1) if last else 1
    previous = last.entry_hash if last else "0" * 64
    created = now_utc()
    safe_detail = redact(detail)
    record = SecureAuditRecord(
        sequence=sequence,
        event_type=event_type,
        outcome=outcome,
        actor_id=actor_id,
        detail=safe_detail,
        previous_hash=previous,
        entry_hash=_digest(
            sequence, event_type, outcome, actor_id, safe_detail, previous, _timestamp(created)
        ),
        created_at=created,
    )
    db.add(record)
    db.flush()
    return record


def verify_audit_chain(db: Session) -> bool:
    records = db.scalars(select(SecureAuditRecord).order_by(SecureAuditRecord.sequence)).all()
    previous = "0" * 64
    expected_sequence = 1
    for record in records:
        if record.sequence != expected_sequence or record.previous_hash != previous:
            return False
        expected = _digest(
            record.sequence,
            record.event_type,
            record.outcome,
            record.actor_id,
            record.detail,
            record.previous_hash,
            _timestamp(record.created_at),
        )
        if not hmac.compare_digest(expected, record.entry_hash):
            return False
        previous = record.entry_hash
        expected_sequence += 1
    return True


def audit_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(SecureAuditRecord)) or 0)
