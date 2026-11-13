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
