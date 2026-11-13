import os
import uuid
from pathlib import Path

os.environ["ASSISTANT_DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ASSISTANT_AUTH_REQUIRED"] = "false"
os.environ["ASSISTANT_OPA_REQUIRED"] = "false"
os.environ["ASSISTANT_SECURITY_DIR"] = ".test-security"

import pytest
from fastapi.testclient import TestClient

from backend.core.config import get_settings
from backend.database import Base, engine
from backend.main import app


@pytest.fixture
def client():
    get_settings().workspace_dir = Path(".test-workspaces") / uuid.uuid4().hex
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(bind=engine)
