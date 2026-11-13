from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.models.entities import (
    Approval,
    AuthSession,
    EncryptedSecret,
    SecureAuditRecord,
    SecurityFinding,
    now_utc,
)
from backend.security.audit import append_security_event, verify_audit_chain
from backend.security.content import record_scan
from backend.security.dependencies import AdminDependency, PrincipalDependency
from backend.security.emergency import (
    activate_emergency_stop,
    get_security_state,
    resume_operations,
)
from backend.security.opa import opa_available
from backend.security.sandbox import sandbox_status
from backend.security.schemas import (
    ContentScanRequest,
    ContentScanResult,
    EmergencyRequest,
    SecretMetadata,
    SecretWrite,
    SecureAuditRead,
    SecurityFindingRead,
    SecurityStatus,
)
from backend.security.vault import encrypt_secret

router = APIRouter(prefix="/security", tags=["security"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/status", response_model=SecurityStatus)
def security_status(_: PrincipalDependency, db: Database) -> SecurityStatus:
    state = get_security_state(db)
    sandbox = sandbox_status()
    settings = get_settings()
    active_sessions = db.scalar(
        select(func.count()).select_from(AuthSession).where(
            AuthSession.revoked_at.is_(None), AuthSession.expires_at > now_utc()
        )
    )
    pending = db.scalar(
        select(func.count()).select_from(Approval).where(Approval.status == "pending")
    )
    findings = db.scalar(
        select(func.count())
        .select_from(SecurityFinding)
        .where(SecurityFinding.status == "open")
    )
    return SecurityStatus(
        emergency_stopped=state.emergency_stopped,
        reason=state.reason,
        activated_at=state.activated_at,
        opa_available=opa_available(),
        opa_required=settings.opa_required,
        openshell_available=sandbox.available,
        openshell_enabled=sandbox.enabled,
        sandbox_mode=sandbox.mode,
        audit_chain_valid=verify_audit_chain(db),
        active_sessions=int(active_sessions or 0),
        pending_approvals=int(pending or 0),
        open_findings=int(findings or 0),
    )


@router.post("/emergency-stop", response_model=SecurityStatus)
def stop(payload: EmergencyRequest, principal: AdminDependency, db: Database):
    activate_emergency_stop(db, payload.reason, principal.user_id)
    return security_status(principal, db)


@router.post("/resume", response_model=SecurityStatus)
def resume(_: EmergencyRequest, principal: AdminDependency, db: Database):
    resume_operations(db, principal.user_id)
    return security_status(principal, db)


@router.post("/scan", response_model=ContentScanResult)
def scan(payload: ContentScanRequest, _: PrincipalDependency, db: Database):
    result = record_scan(db, payload.content, payload.source)
    return ContentScanResult(
        safe=result.safe, risk_score=result.risk_score, findings=result.findings
    )


@router.get("/audit", response_model=list[SecureAuditRead])
def secure_audit(_: AdminDependency, db: Database, limit: int = 100):
    safe_limit = max(1, min(limit, 500))
    return list(
        db.scalars(
            select(SecureAuditRecord)
            .order_by(SecureAuditRecord.sequence.desc())
            .limit(safe_limit)
        ).all()
    )


@router.get("/findings", response_model=list[SecurityFindingRead])
def findings(_: AdminDependency, db: Database, limit: int = 100):
    return list(
        db.scalars(
            select(SecurityFinding)
            .order_by(SecurityFinding.created_at.desc())
            .limit(max(1, min(limit, 500)))
        ).all()
    )


@router.get("/secrets", response_model=list[SecretMetadata])
def list_secrets(principal: AdminDependency, db: Database):
    return list(
        db.scalars(
            select(EncryptedSecret)
            .where(EncryptedSecret.user_id == principal.user_id)
            .order_by(EncryptedSecret.name)
        ).all()
    )


@router.post("/secrets", response_model=SecretMetadata, status_code=201)
def save_secret(payload: SecretWrite, principal: AdminDependency, db: Database):
    item = db.scalar(
        select(EncryptedSecret).where(
            EncryptedSecret.user_id == principal.user_id,
            EncryptedSecret.name == payload.name,
        )
    )
    if item is None:
        item = EncryptedSecret(user_id=principal.user_id, name=payload.name, ciphertext="")
        db.add(item)
    item.ciphertext = encrypt_secret(payload.value)
    item.updated_at = now_utc()
    append_security_event(
        db, "secret.write", "success", f"name={payload.name}", principal.user_id
    )
    db.commit()
    db.refresh(item)
    return item


@router.delete("/secrets/{secret_id}", status_code=204)
def delete_secret(secret_id: str, principal: AdminDependency, db: Database):
    item = db.get(EncryptedSecret, secret_id)
    if item is None or item.user_id != principal.user_id:
        raise HTTPException(status_code=404, detail="Secret not found")
    name = item.name
    db.delete(item)
    append_security_event(db, "secret.delete", "success", f"name={name}", principal.user_id)
    db.commit()
    return Response(status_code=204)
