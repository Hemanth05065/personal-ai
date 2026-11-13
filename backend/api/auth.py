import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.models.entities import User, now_utc
from backend.security.auth import (
    DEVICE_COOKIE,
    SESSION_COOKIE,
    create_login,
    create_user,
    revoke_session,
    verify_login,
)
from backend.security.dependencies import PrincipalDependency
from backend.security.schemas import AuthResponse, BootstrapRequest, LoginRequest, UserRead

router = APIRouter(prefix="/auth", tags=["authentication"])
Database = Annotated[Session, Depends(get_db)]


def _set_cookies(response: Response, session_token: str, device_token: str) -> None:
    settings = get_settings()
    max_age = settings.session_hours * 3600
    options = {
        "httponly": True,
        "secure": settings.secure_cookies,
        "samesite": "strict",
        "max_age": max_age,
        "path": "/",
    }
    response.set_cookie(SESSION_COOKIE, session_token, **options)
    response.set_cookie(DEVICE_COOKIE, device_token, **options)


@router.get("/status")
def auth_status(db: Database) -> dict[str, bool]:
    configured = bool(db.scalar(select(func.count()).select_from(User)))
    return {"auth_required": get_settings().auth_required, "configured": configured}


@router.post("/bootstrap", response_model=AuthResponse, status_code=201)
def bootstrap(payload: BootstrapRequest, request: Request, response: Response, db: Database):
    if db.scalar(select(func.count()).select_from(User)):
        raise HTTPException(status_code=409, detail="An administrator already exists")
    try:
        user = create_user(db, payload.username, payload.password, "admin")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    tokens = create_login(
        db, user, payload.device_name, request.cookies.get(DEVICE_COOKIE)
    )
    _set_cookies(response, tokens.session_token, tokens.device_token)
    return AuthResponse(
        user=UserRead.model_validate(user),
        csrf_token=tokens.csrf_token,
        expires_at=tokens.expires_at,
    )


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, request: Request, response: Response, db: Database):
    user = verify_login(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    tokens = create_login(
        db, user, payload.device_name, request.cookies.get(DEVICE_COOKIE)
    )
    _set_cookies(response, tokens.session_token, tokens.device_token)
    return AuthResponse(
        user=UserRead.model_validate(user),
        csrf_token=tokens.csrf_token,
        expires_at=tokens.expires_at,
    )


@router.get("/me", response_model=UserRead)
def me(principal: PrincipalDependency, db: Database) -> User | UserRead:
    if principal.service:
        return UserRead(
            id=principal.user_id,
            username=principal.username,
            role=principal.role,
            disabled=False,
            created_at=now_utc(),
        )
    user = db.get(User, principal.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Session user no longer exists")
    return user


@router.post("/logout", status_code=204)
def logout(principal: PrincipalDependency, response: Response, db: Database) -> Response:
    if principal.session_id:
        revoke_session(db, principal.session_id, principal.user_id)
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(DEVICE_COOKIE, path="/")
    response.status_code = 204
    return response


def valid_csrf(supplied: str | None, expected_hash: str) -> bool:
    from backend.security.auth import hash_token

    return bool(supplied) and hmac.compare_digest(hash_token(supplied), expected_hash)
