from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    model: str


class MessageRead(ORMModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationRead(ORMModel):
    id: str
    title: str
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


class MemoryCreate(BaseModel):
    content: str = Field(min_length=1, max_length=5_000)
    category: str = Field(default="preference", max_length=50)


class MemoryRead(ORMModel):
    id: str
    content: str
    category: str
    enabled: bool
    created_at: datetime


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=10_000)
    action: str = Field(default="information", max_length=100)
    risk_level: int = Field(default=0, ge=0, le=4)
    arguments: dict[str, str | int | bool] = Field(default_factory=dict)


class TaskRead(ORMModel):
    id: str
    title: str
    description: str
    status: str
    risk_level: int
    created_at: datetime


class ApprovalRead(ORMModel):
    id: str
    task_id: str
    action: str
    status: str
    reason: str
    created_at: datetime


class ApprovalDetail(ApprovalRead):
    description: str
    justification: str
    targets: list[str]
    consequences: str


class ToolCallRead(ORMModel):
    id: str
    task_id: str
    tool_name: str
    arguments: str
    status: str
    result: str
    created_at: datetime
    finished_at: datetime | None


class WorkspaceFile(BaseModel):
    path: str
    size: int
    modified_at: datetime


class WorkspaceFileContent(BaseModel):
    path: str
    content: str
    size: int


class ResearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_sources: int = Field(default=3, ge=1, le=5)


class ResearchSource(BaseModel):
    title: str
    url: str
    excerpt: str


class ResearchResponse(BaseModel):
    query: str
    report: str
    sources: list[ResearchSource]


class AuditLogRead(ORMModel):
    id: str
    action: str
    outcome: str
    detail: str
    created_at: datetime


class AutomationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    action: str = Field(max_length=100)
    arguments: dict[str, str | int | bool] = Field(default_factory=dict)
    interval_minutes: int = Field(default=60, ge=1, le=43_200)


class AutomationRead(ORMModel):
    id: str
    title: str
    action: str
    arguments: str
    interval_minutes: int
    enabled: bool
    next_run: datetime
    last_run: datetime | None
    created_at: datetime
