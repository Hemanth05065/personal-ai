import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.database import Base, engine
from backend.main import app


def test_bootstrap_device_session_and_csrf():
    settings = get_settings()
    old_auth = settings.auth_required
    old_key = settings.api_key
    settings.auth_required = True
    settings.api_key = None
    settings.workspace_dir = Path(".test-workspaces") / uuid.uuid4().hex
    Base.metadata.create_all(bind=engine)
    try:
        with TestClient(app) as client:
            status = client.get("/api/v1/auth/status")
            assert status.status_code == 200
            assert status.json()["configured"] is False
            created = client.post(
                "/api/v1/auth/bootstrap",
                json={
                    "username": "owner",
                    "password": "LongLocalPassword!42",
                    "device_name": "pytest browser",
                },
            )
            assert created.status_code == 201
            csrf = created.json()["csrf_token"]
            assert client.get("/api/v1/auth/me").status_code == 200
            assert (
                client.post("/api/v1/memory", json={"content": "missing csrf"}).status_code == 403
            )
            allowed = client.post(
                "/api/v1/memory",
                json={"content": "csrf protected"},
                headers={"X-CSRF-Token": csrf},
            )
            assert allowed.status_code == 201
    finally:
        settings.auth_required = old_auth
        settings.api_key = old_key
        Base.metadata.drop_all(bind=engine)


def test_cors_preflight_is_not_blocked_by_auth():
    settings = get_settings()
    old_auth = settings.auth_required
    settings.auth_required = True
    Base.metadata.create_all(bind=engine)
    try:
        with TestClient(app) as client:
            preflight = client.options(
                "/api/v1/memory",
                headers={
                    "Origin": "http://localhost:5173",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type,x-csrf-token",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"
            # The real request without a session is still rejected.
            assert client.get("/api/v1/memory").status_code == 401
    finally:
        settings.auth_required = old_auth
        Base.metadata.drop_all(bind=engine)


def test_last_seen_is_not_written_on_every_request():
    """Reads must stay reads: "last seen" is refreshed at most once a minute."""
    from datetime import timedelta

    from backend.database import SessionLocal
    from backend.models.entities import AuthSession
    from backend.security.auth import authenticate_session, create_login, create_user

    Base.metadata.create_all(bind=engine)
    try:
        with SessionLocal() as db:
            user = create_user(db, "seen-user", "LongLocalPassword!42", "admin")
            tokens = create_login(db, user, "pytest")
            session = db.scalars(__import__("sqlalchemy").select(AuthSession)).one()
            first = session.last_seen

            assert authenticate_session(db, tokens.session_token, tokens.device_token)
            db.refresh(session)
            assert session.last_seen == first  # a request within the minute writes nothing

            session.last_seen = first - timedelta(minutes=2)
            db.commit()
            assert authenticate_session(db, tokens.session_token, tokens.device_token)
            db.refresh(session)
            assert session.last_seen > first - timedelta(minutes=2)  # stale, so refreshed
    finally:
        Base.metadata.drop_all(bind=engine)
