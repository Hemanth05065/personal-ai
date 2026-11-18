from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.entities import AuditLog, Memory
from backend.models.schemas import MemoryCreate, MemoryRead
from backend.security.content import record_scan
from backend.security.dependencies import OperatorDependency

router = APIRouter(prefix="/memory", tags=["memory"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[MemoryRead])
def list_memories(db: Database) -> list[Memory]:
    return list(db.scalars(select(Memory).order_by(Memory.created_at.desc())).all())


@router.post("", response_model=MemoryRead, status_code=201)
def create_memory(payload: MemoryCreate, principal: OperatorDependency, db: Database) -> Memory:
    # Memories are inserted into every chat's system prompt, so an instruction
    # hidden in one would apply to all future conversations. Block, don't just flag.
    scan = record_scan(db, payload.content, "memory")
    if not scan.safe:
        raise HTTPException(
            status_code=422,
            detail="This memory reads like an instruction to override the assistant's rules, so it was not saved.",
        )
    memory = Memory(
        content=payload.content, category=payload.category, created_by=principal.user_id
    )
    db.add(memory)
    db.add(AuditLog(action="memory.create", outcome="success", detail=payload.category))
    db.commit()
    db.refresh(memory)
    return memory


@router.delete("/{memory_id}", status_code=204)
def delete_memory(memory_id: str, _: OperatorDependency, db: Database) -> Response:
    memory = db.get(Memory, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(memory)
    db.add(AuditLog(action="memory.delete", outcome="success", detail=memory_id))
    db.commit()
    return Response(status_code=204)
