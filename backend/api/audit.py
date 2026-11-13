from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.entities import AuditLog
from backend.models.schemas import AuditLogRead

router = APIRouter(prefix="/audit", tags=["audit"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AuditLogRead])
def list_audit_logs(
    db: Database,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AuditLog]:
    return list(
        db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit)).all()
    )
