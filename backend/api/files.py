import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.models.schemas import WorkspaceFile, WorkspaceFileContent
from backend.security.dependencies import OperatorDependency
from backend.services.tools import ToolError, list_files, read_file
from backend.services.versions import UndoRefused, undo_write

router = APIRouter(prefix="/files", tags=["files"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[WorkspaceFile])
def get_files(db: Database) -> list[dict]:
    del db
    return list_files(get_settings()).data


@router.get("/{file_path:path}", response_model=WorkspaceFileContent)
def get_file(file_path: str, db: Database) -> dict:
    del db
    try:
        result = read_file(get_settings(), {"path": file_path})
    except ToolError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    data = result.data
    if isinstance(data, str):
        return json.loads(data)
    return data


@router.post("/undo/{call_id}")
def undo_file_write(call_id: str, principal: OperatorDependency, db: Database) -> dict:
    """Put a file back the way it was before an assistant write."""
    try:
        return {"message": undo_write(db, call_id, get_settings(), principal.user_id)}
    except UndoRefused as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.reason) from exc
