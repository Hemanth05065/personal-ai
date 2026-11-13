"""Streaming chat: event format, saving, errors, early stop, and Ollama NDJSON parsing."""

import asyncio
import json

import httpx
import pytest

from backend.api.chat import chat_stream
from backend.core.config import get_settings
from backend.database import SessionLocal
from backend.models.schemas import ChatRequest
from backend.security.auth import Principal
from backend.services.ollama import OllamaClient, OllamaUnavailable

LOCAL_ADMIN = Principal("local-development", "local", "admin", service=True)


def _events(body: str) -> list[dict]:
    return [json.loads(line) for line in body.splitlines() if line.strip()]


def _fake_stream(chunks, fail_after=None):
    async def stream_chat(self, messages, memories, tools=None, system_extra=""):
        for index, chunk in enumerate(chunks):
            if fail_after is not None and index == fail_after:
                raise OllamaUnavailable("model crashed")
            yield chunk

    return stream_chat


def _assistant_messages(client, conversation_id):
    detail = client.get(f"/api/v1/chat/conversations/{conversation_id}").json()
    return [item["content"] for item in detail["messages"] if item["role"] == "assistant"]


def test_stream_sends_events_and_saves_full_reply(client, monkeypatch):
    monkeypatch.setattr(OllamaClient, "stream_chat", _fake_stream(["Hel", "lo ", "there"]))
    response = client.post("/api/v1/chat/stream", json={"message": "Hi"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")

    events = _events(response.text)
    assert [item["type"] for item in events] == ["start", "delta", "delta", "delta", "done"]
    assert "".join(item["text"] for item in events if item["type"] == "delta") == "Hello there"
    assert events[-1]["message_id"]
    assert _assistant_messages(client, events[0]["conversation_id"]) == ["Hello there"]


def test_stream_reports_error_and_keeps_partial_text(client, monkeypatch):
    monkeypatch.setattr(OllamaClient, "stream_chat", _fake_stream(["Part", "never"], fail_after=1))
    events = _events(client.post("/api/v1/chat/stream", json={"message": "Hi"}).text)
    assert [item["type"] for item in events] == ["start", "delta", "error"]
    assert events[-1]["detail"] == "model crashed"
    assert _assistant_messages(client, events[0]["conversation_id"]) == ["Part"]


def test_stream_continues_an_existing_conversation(client, monkeypatch):
    monkeypatch.setattr(OllamaClient, "stream_chat", _fake_stream(["One"]))
    first = _events(client.post("/api/v1/chat/stream", json={"message": "First"}).text)
    conversation_id = first[0]["conversation_id"]
    monkeypatch.setattr(OllamaClient, "stream_chat", _fake_stream(["Two"]))
    second = _events(client.post(
        "/api/v1/chat/stream", json={"message": "Second", "conversation_id": conversation_id}
    ).text)
    assert second[0]["conversation_id"] == conversation_id
    assert _assistant_messages(client, conversation_id) == ["One", "Two"]


def test_stream_unknown_conversation_is_404(client):
    response = client.post("/api/v1/chat/stream", json={"message": "Hi", "conversation_id": "missing"})
    assert response.status_code == 404


def test_stopping_early_saves_what_arrived(client, monkeypatch):
    """Simulates the Stop button: the client stops reading after the first piece."""
    monkeypatch.setattr(OllamaClient, "stream_chat", _fake_stream(["Kept ", "text", " never sent"]))

    async def read_two_pieces_then_stop() -> str:
        with SessionLocal() as db:
            response = await chat_stream(ChatRequest(message="Hi"), LOCAL_ADMIN, db)
        iterator = response.body_iterator
        start = json.loads(await iterator.__anext__())
        await iterator.__anext__()  # "Kept "
        await iterator.__anext__()  # "text"
        await iterator.aclose()  # what Starlette does when the browser disconnects
        return start["conversation_id"]

    conversation_id = asyncio.run(read_two_pieces_then_stop())
    assert _assistant_messages(client, conversation_id) == ["Kept text"]


# ---------- Ollama NDJSON parsing ----------

def _client_with(lines: list[str], status: int = 200) -> OllamaClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["stream"] is True and body["think"] is False
        return httpx.Response(status, content="\n".join(lines).encode())

    return OllamaClient(get_settings(), transport=httpx.MockTransport(handler))


async def _collect(ollama: OllamaClient) -> list[str]:
    return [piece async for piece in ollama.stream_chat([{"role": "user", "content": "hi"}], [])]


def test_ollama_stream_parses_ndjson_until_done():
    lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        "",
        json.dumps({"message": {"content": " world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
        json.dumps({"message": {"content": "after done is ignored"}, "done": False}),
    ]
    assert asyncio.run(_collect(_client_with(lines))) == ["Hello", " world"]


def test_ollama_stream_raises_on_error_line_or_http_error():
    with pytest.raises(OllamaUnavailable, match="model not found"):
        asyncio.run(_collect(_client_with([json.dumps({"error": "model not found"})])))
    with pytest.raises(OllamaUnavailable):
        asyncio.run(_collect(_client_with(["{}"], status=500)))


def test_ollama_stream_turns_tool_calls_into_requests():
    from backend.services.ollama import ToolRequest

    lines = [
        json.dumps({"message": {"content": "", "tool_calls": [
            {"function": {"name": "write_file", "arguments": {"path": "a.txt", "content": "x"}}},
            {"function": {"name": "read_file", "arguments": "{\"path\": \"b.txt\"}"}},
        ]}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]
    assert asyncio.run(_collect(_client_with(lines))) == [
        ToolRequest("write_file", {"path": "a.txt", "content": "x"}),
        ToolRequest("read_file", {"path": "b.txt"}),
    ]
