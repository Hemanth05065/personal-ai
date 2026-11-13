from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.database import get_db
from backend.models.entities import AuditLog, Conversation, Memory, Message
from backend.models.schemas import (
    ChatRequest,
    ChatResponse,
    ConversationDetail,
    ConversationRead,
)
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
def delete_conversation(conversation_id: str, db: Database) -> Response:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    db.delete(conversation)
    db.add(
        AuditLog(action="conversation.delete", outcome="success", detail=conversation_id)
    )
    db.commit()
    return Response(status_code=204)


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, db: Database) -> ChatResponse:
    settings = get_settings()
    conversation = db.get(Conversation, payload.conversation_id) if payload.conversation_id else None
    if payload.conversation_id and conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if conversation is None:
        conversation = Conversation(title=payload.message[:80])
        db.add(conversation)
        db.flush()

    db.add(Message(conversation_id=conversation.id, role="user", content=payload.message))
    db.commit()

    history = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.desc())
        .limit(settings.max_context_messages)
    ).all()
    memories = db.scalars(select(Memory).where(Memory.enabled.is_(True)).limit(20)).all()
    messages = [{"role": item.role, "content": item.content} for item in reversed(history)]

    try:
        answer = await OllamaClient(settings).chat(messages, [item.content for item in memories])
    except OllamaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    db.add(Message(conversation_id=conversation.id, role="assistant", content=answer))
    db.commit()
    return ChatResponse(conversation_id=conversation.id, message=answer, model=settings.model)
