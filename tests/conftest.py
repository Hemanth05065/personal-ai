import os
import shutil
import uuid
from pathlib import Path

os.environ["ASSISTANT_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ASSISTANT_AUTH_REQUIRED"] = "false"
os.environ["ASSISTANT_OPA_REQUIRED"] = "false"
os.environ["ASSISTANT_SECURITY_DIR"] = ".test-security"
# The background loop would race with tests that call the scheduler directly.
os.environ["ASSISTANT_SCHEDULER_ENABLED"] = "false"

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.database import Base, SessionLocal, engine
from backend.main import app
from backend.security.auth import create_user
from backend.security.throttle import login_throttle

TEST_PASSWORD = "LongLocalPassword!42"
# All test files go here (the system temp folder may be locked down on this machine).
TEST_ROOT = Path(".test-workspaces")


@pytest.fixture(scope="session", autouse=True)
def remove_test_files_after_run():
    """Delete everything tests wrote once the run ends, including folders a test
    set up itself and files Windows kept locked until their handles closed."""
    yield
    shutil.rmtree(TEST_ROOT, ignore_errors=True)


@pytest.fixture
def client():
    workspace = TEST_ROOT / uuid.uuid4().hex
    get_settings().workspace_dir = workspace
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
    shutil.rmtree(workspace, ignore_errors=True)


@pytest.fixture
def scratch_dir():
    """A per-test folder for files a test creates directly."""
    path = TEST_ROOT / "scratch" / uuid.uuid4().hex
    path.mkdir(parents=True)
    yield path.resolve()
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def sign_in(client):
    """Turn real authentication on and return a factory for signed-in clients.

    sign_in("viewer") creates a user with that role, logs in on its own TestClient
    (its own cookies) and sets the CSRF header, so tests exercise the real
    middleware instead of the auth-disabled shortcut.
    """
    settings = get_settings()
    old_auth, old_key = settings.auth_required, settings.api_key
    settings.auth_required = True
    settings.api_key = None
    login_throttle.reset()
    opened: list[TestClient] = []

    def factory(role: str = "admin", username: str | None = None) -> TestClient:
        name = username or f"{role}-{uuid.uuid4().hex[:8]}"
        with SessionLocal() as db:
            create_user(db, name, TEST_PASSWORD, role)
            db.commit()
        user_client = TestClient(app)
        opened.append(user_client)
        response = user_client.post(
            "/api/v1/auth/login",
            json={"username": name, "password": TEST_PASSWORD, "device_name": "pytest"},
        )
        assert response.status_code == 200, response.text
        user_client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        user_client.user = response.json()["user"]
        return user_client

    yield factory
    for item in opened:
        item.close()
    settings.auth_required = old_auth
    settings.api_key = old_key
    login_throttle.reset()
