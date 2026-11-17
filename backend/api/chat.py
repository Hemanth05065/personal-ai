import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.settings import autopilot_enabled
from backend.core.config import get_settings
from backend.database import SessionLocal, get_db
from backend.models.entities import AuditLog, Conversation, Memory, Message
from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationRead,
)
from backend.security.content import record_scan
from backend.security.dependencies import OperatorDependency, PrincipalDependency
from backend.services.agent import run_agent
from backend.services.ollama import OllamaClient, OllamaUnavailable, model_installed
from backend.services.routing import (
    EXAMPLE_INPUT_PROMPT,
    choose_model,
    extract_example_input,
    with_reminder,
    without_big,
)

router = APIRouter(prefix="/chat", tags=["chat"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(db: Database) -> list[Conversation]:
    return list(db.scalars(select(Conversation).order_by(Conversation.created_at.desc())).all())


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: str, db: Database) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conversation.messages.sort(key=lambda message: message.created_at)
    return conversation


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str, _: OperatorDependency, db: Database) -> Response:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conversation)
    db.add(AuditLog(action="conversation.delete", outcome="success", detail=conversation_id))
    db.commit()
    return Response(status_code=204)


def _prepare(payload: ChatRequest, db: Session) -> tuple[str, list[dict[str, str]], list[str]]:
    """Scan and store the user's message; return the conversation id, history and memories."""
    settings = get_settings()
    # The owner's own message is recorded as a finding but not blocked.
    record_scan(db, payload.message, "chat")
    conversation = (
        db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
    )
    if payload.conversation_id and conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation is None:
        conversation = Conversation(title=payload.message[:80])
        db.add(conversation)
        db.flush()

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.message))
    # Commit before talking to the model so no write transaction stays open meanwhile.
    db.commit()

    history = db.scalars(
        select(Message)
        # tool_event rows are UI records of proposals, not part of the model's dialogue.
        .where(Message.conversation_id == conversation.id, Message.role.in_(("user", "assistant")))
        .order_by(Message.created_at.desc())
        .limit(settings.max_context_messages)
    ).all()
    memories = db.scalars(select(Memory).where(Memory.enabled.is_(True)).limit(20)).all()
    messages = [{"role": item.role, "content": item.content} for item in reversed(history)]
    return conversation.id, messages, [item.content for item in memories]


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Database) -> ChatResponse:
    settings = get_settings()
    conversation_id, messages, memories = await run_in_threadpool(_prepare, payload, db)
    try:
        answer = await OllamaClient(settings).chat(messages, memories)
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    await run_in_threadpool(_save_message, conversation_id, "assistant", answer)
    return ChatResponse(conversation_id=conversation_id, message=answer, model=settings.model)


class ExampleInputRequest(BaseModel):
    code: str = Field(min_length=1, max_length=60_000)


@router.post("/example-input")
async def example_input(payload: ExampleInputRequest, principal: PrincipalDependency) -> dict:
    """A sample input for a Python program, so the Output panel's self-test can run it.

    Uses the fast coder. The result only ever goes to the program's input() inside the
    sandbox, never to a tool or a file.
    """
    del principal  # any signed-in user; the answer stays in their own browser sandbox
    settings = get_settings()
    client = OllamaClient(
        settings,
        model=settings.coder_model or settings.model,
        context_tokens=settings.coder_context_tokens,
    )
    prompt = EXAMPLE_INPUT_PROMPT.replace("{code}", payload.code)
    try:
        reply = await client.chat([{"role": "user", "content": prompt}], [])
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"input": extract_example_input(reply)}


def _event(data: dict) -> str:
    return json.dumps(data) + "\n"


def _save_message(conversation_id: str, role: str, content: str) -> str:
    # Own session: the request's session may already be closed while the body streams.
    with SessionLocal() as db:
        message = Message(conversation_id=conversation_id, role=role, content=content)
        db.add(message)
        db.commit()
        return message.id


@router.post("/stream")
async def chat_stream(
    payload: ChatRequest, principal: PrincipalDependency, db: Database
) -> StreamingResponse:
    """Stream a reply as newline-delimited JSON events.

    {"type": "start", "conversation_id", "model", "coding", "big"}  once, first
    {"type": "delta", "text"}                       for each piece of the reply
    {"type": "tool", "tool": {...}}                 when the model asked for a tool (see agent.py)
    {"type": "done", "message_id"}                  when the reply is complete
    {"type": "error", "detail"}                     if the model fails mid-way

    Whatever text arrived is saved even if the client stops the reply early.
    """
    settings = get_settings()
    # Database work goes to a worker thread; the event loop must never block on it.
    conversation_id, messages, memories = await run_in_threadpool(_prepare, payload, db)
    autopilot = await run_in_threadpool(autopilot_enabled, principal.user_id)
    # Coding requests go to the coding model with a bigger window.
    choice = choose_model(settings, payload.message)
    if choice.big and not await model_installed(settings, choice.model):
        choice = without_big(settings, choice)
    # The model sees the coding checklist after the request; the saved chat doesn't.
    model_messages = with_reminder(messages) if choice.coding else messages
    ollama = OllamaClient(
        settings,
        model=choice.model,
        context_tokens=choice.context_tokens,
        read_timeout=600 if choice.big else 120,
    )

    async def events() -> AsyncIterator[str]:
        parts: list[str] = []
        message_id: str | None = None
        error: str | None = None
        completed = False
        yield _event(
            {
                "type": "start",
                "conversation_id": conversation_id,
                "model": choice.model,
                "coding": choice.coding,
                "big": choice.big,
            }
        )
        try:
            async for event in run_agent(
                ollama, principal, model_messages, memories, autopilot, choice.guidance
            ):
                if event["type"] == "delta":
                    parts.append(event["text"])
                else:
                    await run_in_threadpool(
                        _save_message, conversation_id, "tool_event", json.dumps(event["tool"])
                    )
                yield _event(event)
            completed = True
        except OllamaUnavailable as exc:
            error = str(exc)
        finally:
            # Runs on normal end, on error, and when the client disconnects (Stop).
            # Stays synchronous: a cancelled generator can't reliably await. One short write.
            if parts:
                message_id = _save_message(conversation_id, "assistant", "".join(parts))
        if error:
            yield _event({"type": "error", "detail": error})
        elif completed:
            yield _event({"type": "done", "message_id": message_id})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
