import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from backend.security.dependencies import OperatorDependency
from backend.services.ollama import OllamaClient, OllamaUnavailable

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
    db.add(
        AuditLog(action="conversation.delete", outcome="success", detail=conversation_id)
    )
    db.commit()
    return Response(status_code=204)


def _prepare(payload: ChatRequest, db: Session) -> tuple[str, list[dict[str, str]], list[str]]:
    """Scan and store the user's message; return the conversation id, history and memories."""
    settings = get_settings()
    # The owner's own message is recorded as a finding but not blocked.
    record_scan(db, payload.message, "chat")
    conversation = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
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
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(settings.max_context_messages)
    ).all()
    memories = db.scalars(select(Memory).where(Memory.enabled.is_(True)).limit(20)).all()
    messages = [{"role": item.role, "content": item.content} for item in reversed(history)]
    return conversation.id, messages, [item.content for item in memories]


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Database) -> ChatResponse:
    settings = get_settings()
    conversation_id, messages, memories = _prepare(payload, db)
    try:
        answer = await OllamaClient(settings).chat(messages, memories)
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add(Message(conversation_id=conversation_id, role="assistant", content=answer))
    db.commit()
    return ChatResponse(conversation_id=conversation_id, message=answer, model=settings.model)


def _event(data: dict) -> str:
    return json.dumps(data) + "\n"


def _save_assistant_message(conversation_id: str, content: str) -> str:
    # Own session: the request's session may already be closed while the body streams.
    with SessionLocal() as db:
        message = Message(conversation_id=conversation_id, role="assistant", content=content)
        db.add(message)
        db.commit()
        return message.id


@router.post("/stream")
async def chat_stream(payload: ChatRequest, db: Database) -> StreamingResponse:
    """Stream a reply as newline-delimited JSON events.

    {"type": "start", "conversation_id", "model"}  once, first
    {"type": "delta", "text"}                       for each piece of the reply
    {"type": "done", "message_id"}                  when the reply is complete
    {"type": "error", "detail"}                     if the model fails mid-way

    Whatever text arrived is saved even if the client stops the reply early.
    """
    settings = get_settings()
    conversation_id, messages, memories = _prepare(payload, db)

    async def events() -> AsyncIterator[str]:
        parts: list[str] = []
        message_id: str | None = None
        error: str | None = None
        completed = False
        yield _event({"type": "start", "conversation_id": conversation_id, "model": settings.model})
        try:
            async for text in OllamaClient(settings).stream_chat(messages, memories):
                parts.append(text)
                yield _event({"type": "delta", "text": text})
            completed = True
        except OllamaUnavailable as exc:
            error = str(exc)
        finally:
            # Runs on normal end, on error, and when the client disconnects (Stop).
            if parts:
                message_id = _save_assistant_message(conversation_id, "".join(parts))
        if error:
            yield _event({"type": "error", "detail": error})
        elif completed:
            yield _event({"type": "done", "message_id": message_id})

    return StreamingResponse(
        events(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
