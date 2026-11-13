from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class BootstrapRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=256)
    device_name: str = Field(default="Local browser", min_length=2, max_length=200)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    device_name: str = Field(default="Local browser", min_length=2, max_length=200)


class UserRead(ORMModel):
    id: str
    username: str
    role: str
    disabled: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserRead
    csrf_token: str
    expires_at: datetime


class EmergencyRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class SecurityStatus(BaseModel):
    emergency_stopped: bool
    reason: str
    activated_at: datetime | None
    opa_available: bool
    opa_required: bool
    openshell_available: bool
    openshell_enabled: bool
    sandbox_mode: str
    audit_chain_valid: bool
    active_sessions: int
    pending_approvals: int
    open_findings: int


class SecretWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    value: str = Field(min_length=1, max_length=20_000)


class SecretMetadata(ORMModel):
    id: str
    name: str
    created_at: datetime
    updated_at: datetime


class ContentScanRequest(BaseModel):
    content: str = Field(min_length=1, max_length=100_000)
    source: str = Field(default="external", max_length=100)


class ContentScanResult(BaseModel):
    safe: bool
    risk_score: int
    findings: list[str]


class SecureAuditRead(ORMModel):
    id: str
    sequence: int
    event_type: str
    outcome: str
    actor_id: str | None
    detail: str
    previous_hash: str
    entry_hash: str
    created_at: datetime


class SecurityFindingRead(ORMModel):
    id: str
    category: str
    severity: str
    source: str
    detail: str
    status: str
    created_at: datetime
