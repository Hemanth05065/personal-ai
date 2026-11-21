from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import SessionLocal, get_db
from backend.models.entities import UserSetting, now_utc
from backend.security.audit import append_security_event
from backend.security.dependencies import PrincipalDependency, has_role

router = APIRouter(prefix="/settings", tags=["settings"])
Database = Annotated[Session, Depends(get_db)]


class SettingsRead(BaseModel):
    autopilot: bool
    # Search first: everyday questions are searched on DuckDuckGo before the model answers.
    web_search: bool
    # False when the server has web access off entirely (ASSISTANT_WEB_LOOKUPS_ENABLED=false).
    web_available: bool


class SettingsUpdate(BaseModel):
    autopilot: bool | None = None
    web_search: bool | None = None


def autopilot_enabled(user_id: str) -> bool:
    """Do-it mode for this user (off unless they turned it on)."""
    with SessionLocal() as db:
        setting = db.get(UserSetting, user_id)
        return bool(setting and setting.autopilot)


def _web_search(setting: UserSetting | None) -> bool:
    settings = get_settings()
    if not settings.web_lookups_enabled:
        return False
    if setting is None or setting.web_search is None:
        return settings.web_search_first
    return setting.web_search


def web_search_enabled(user_id: str) -> bool:
    """Search first for this user: their own choice, else the server default."""
    with SessionLocal() as db:
        return _web_search(db.get(UserSetting, user_id))


def _read(setting: UserSetting | None) -> SettingsRead:
    return SettingsRead(
        autopilot=bool(setting and setting.autopilot),
        web_search=_web_search(setting),
        web_available=get_settings().web_lookups_enabled,
    )


@router.get("/me", response_model=SettingsRead)
def get_my_settings(principal: PrincipalDependency, db: Database) -> SettingsRead:
    return _read(db.get(UserSetting, principal.user_id))


@router.put("/me", response_model=SettingsRead)
def update_my_settings(payload: SettingsUpdate, principal: PrincipalDependency, db: Database) -> SettingsRead:
    if payload.autopilot and not has_role(principal, "operator"):
        raise HTTPException(status_code=403, detail="Viewers can’t make changes, so Do-it mode isn’t available.")
    setting = db.get(UserSetting, principal.user_id) or UserSetting(user_id=principal.user_id)
    if payload.autopilot is not None:
        changed = bool(setting.autopilot) != payload.autopilot
        setting.autopilot = payload.autopilot
        if changed:
            # Turning autonomy on or off is a security-relevant event.
            append_security_event(
                db, "settings.do_it_mode", "on" if payload.autopilot else "off", "", principal.user_id
            )
    if payload.web_search is not None:
        if bool(_web_search(setting)) != payload.web_search:
            # Whether everyday questions leave the computer is a privacy choice: record it.
            append_security_event(
                db, "settings.web_search", "on" if payload.web_search else "off", "", principal.user_id
            )
        setting.web_search = payload.web_search
    setting.updated_at = now_utc()
    db.add(setting)
    db.commit()
    return _read(setting)
