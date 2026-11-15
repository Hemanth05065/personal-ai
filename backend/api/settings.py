from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import SessionLocal, get_db
from backend.models.entities import UserSetting, now_utc
from backend.security.audit import append_security_event
from backend.security.dependencies import PrincipalDependency, has_role

router = APIRouter(prefix="/settings", tags=["settings"])
Database = Annotated[Session, Depends(get_db)]


class SettingsRead(BaseModel):
    autopilot: bool


class SettingsUpdate(BaseModel):
    autopilot: bool


def autopilot_enabled(user_id: str) -> bool:
    """Do-it mode for this user (off unless they turned it on)."""
    with SessionLocal() as db:
        setting = db.get(UserSetting, user_id)
        return bool(setting and setting.autopilot)


@router.get("/me", response_model=SettingsRead)
def get_my_settings(principal: PrincipalDependency, db: Database) -> SettingsRead:
    setting = db.get(UserSetting, principal.user_id)
    return SettingsRead(autopilot=bool(setting and setting.autopilot))


@router.put("/me", response_model=SettingsRead)
def update_my_settings(payload: SettingsUpdate, principal: PrincipalDependency, db: Database) -> SettingsRead:
    if payload.autopilot and not has_role(principal, "operator"):
        raise HTTPException(status_code=403, detail="Viewers can’t make changes, so Do-it mode isn’t available.")
    setting = db.get(UserSetting, principal.user_id) or UserSetting(user_id=principal.user_id)
    changed = setting.autopilot != payload.autopilot
    setting.autopilot = payload.autopilot
    setting.updated_at = now_utc()
    db.add(setting)
    if changed:
        # Turning autonomy on or off is a security-relevant event.
        append_security_event(
            db, "settings.do_it_mode", "on" if payload.autopilot else "off", "", principal.user_id
        )
    db.commit()
    return SettingsRead(autopilot=setting.autopilot)
